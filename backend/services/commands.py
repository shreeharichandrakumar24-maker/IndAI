"""Direct command execution (FAST): resolve, default, validate, write, audit.

ONE call creates/updates rows (no LLM inside — target <500 ms), writes a
factory_memory VOICE_COMMAND entry with everything undo needs, and returns
a spoken-friendly one-sentence summary. ASK mode routes the same resolved
params into the existing proposal flow instead of executing.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4
import re

from fastapi import HTTPException
from sqlalchemy import text as _sql
from sqlalchemy.orm import Session

from backend.models.models import (
    AIRecommendation,
    Employee,
    FactoryMemory,
    Incident,
    Machine,
    Maintenance,
    Order,
    ProductionRun,
    Task,
    WorkPlan,
    WorkerCredential,
)
from backend.services import command_policy as pol
from backend.services.resolve import resolve_one

DONE_TASK = {"DONE", "COMPLETED", "CANCELLED"}


DONE_TASK = {"DONE", "COMPLETED", "CANCELLED"}


# ---------- small helpers ----------

def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    try:
        return dt.isoformat() if dt else None
    except Exception:
        return None


def _parse_uuid(value):
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _task_dict(t: Task) -> dict:
    return {"id": str(t.id), "name": t.name, "status": t.status,
            "employee_id": str(t.employee_id) if t.employee_id else None,
            "machine_id": str(t.machine_id) if t.machine_id else None,
            "order_id": str(t.order_id) if t.order_id else None,
            "deadline": _iso(t.deadline), "priority": t.priority,
            "progress": t.progress, "updated_at": _iso(t.updated_at)}


def _profile_skills(db: Session) -> list:
    try:
        from backend.models.models import FactoryProfile
        prof = db.query(FactoryProfile).filter(
            FactoryProfile.status == "APPROVED").order_by(
            FactoryProfile.updated_at.desc()).first()
        if prof is not None and isinstance(prof.profile, dict):
            return prof.profile.get("skills") or []
    except Exception:
        pass
    return []


def _busy_machines(db: Session) -> set:
    try:
        return {r.machine_id for r in db.query(ProductionRun).filter(
            ProductionRun.status.in_(["IN_PROGRESS", "RUNNING"])).all() if r.machine_id}
    except Exception:
        return set()


def _open_incident_machines(db: Session) -> set:
    try:
        return {i.machine_id for i in db.query(Incident).filter(
            Incident.status == "OPEN").all() if i.machine_id}
    except Exception:
        return set()


# One round trip for every rule input: employees, machines, worker codes,
# open-incident machines, busy machines, open-task counts and the active
# factory profile (skills + autonomy). Keeps a command well under the 500 ms
# target even over a remote database.
_SNAP_SQL = _sql("""
SELECT
 (SELECT COALESCE(jsonb_agg(jsonb_build_object(
     'id', id::text, 'name', name, 'role', role, 'status', status,
     'availability', availability, 'skills', skills)), '[]'::jsonb)
  FROM employees) AS employees,
 (SELECT COALESCE(jsonb_agg(jsonb_build_object(
     'id', id::text, 'name', name, 'machine_type', machine_type,
     'status', status, 'health_status', health_status)), '[]'::jsonb)
  FROM machines) AS machines,
 (SELECT COALESCE(jsonb_object_agg(employee_id::text, employee_code), '{}'::jsonb)
  FROM worker_credentials WHERE employee_code IS NOT NULL) AS codes,
 (SELECT COALESCE(jsonb_agg(DISTINCT machine_id::text), '[]'::jsonb)
  FROM incidents WHERE status = 'OPEN' AND machine_id IS NOT NULL) AS open_inc,
 (SELECT COALESCE(jsonb_agg(DISTINCT machine_id::text), '[]'::jsonb)
  FROM production_runs WHERE status IN ('IN_PROGRESS', 'RUNNING')
    AND machine_id IS NOT NULL) AS busy,
 (SELECT COALESCE(jsonb_object_agg(employee_id::text, c), '{}'::jsonb)
  FROM (SELECT employee_id, count(*) AS c FROM tasks
        WHERE employee_id IS NOT NULL
          AND status IN ('PENDING', 'IN_PROGRESS', 'PLANNED')
        GROUP BY employee_id) s) AS counts,
 (SELECT jsonb_build_object(
     'skills', profile->'skills',
     'ai_preferences', profile->'ai_preferences')
  FROM factory_profile WHERE status = 'APPROVED'
  ORDER BY updated_at DESC LIMIT 1) AS profile,
 (SELECT COALESCE(jsonb_agg(jsonb_build_object(
     'name', name, 'employee_id', employee_id::text,
     'order_id', order_id::text, 'created_at', created_at)), '[]'::jsonb)
  FROM tasks WHERE created_at >= now() - interval '90 seconds') AS recent_tasks
""")


class _Snap:
    """One bulk fetch shared across spans + best picks (single query)."""
    def __init__(self, db: Session):
        row = {}
        try:
            row = dict(db.execute(_SNAP_SQL).mappings().first() or {})
        except Exception:
            db.rollback()
        self.employees = [SimpleNamespace(
            id=_parse_uuid(e.get("id")), name=e.get("name"), role=e.get("role"),
            status=e.get("status"), availability=e.get("availability"),
            skills=e.get("skills")) for e in (row.get("employees") or [])]
        self.machines = [SimpleNamespace(
            id=_parse_uuid(m.get("id")), name=m.get("name"),
            machine_type=m.get("machine_type"), status=m.get("status"),
            health_status=m.get("health_status")) for m in (row.get("machines") or [])]
        self.codes = {_parse_uuid(k): v for k, v in (row.get("codes") or {}).items()}
        self.open_inc = {_parse_uuid(x) for x in (row.get("open_inc") or [])}
        self.busy = {_parse_uuid(x) for x in (row.get("busy") or [])}
        self.counts = {_parse_uuid(k): int(v) for k, v in (row.get("counts") or {}).items()}
        prof = row.get("profile") or {}
        prof = prof if isinstance(prof, dict) else {}
        self.skills = prof.get("skills") or []
        prefs = prof.get("ai_preferences") or {}
        self.autonomy = "ASK" if str(prefs.get("autonomy", "FAST")).upper() == "ASK" else "FAST"
        self.recent_tasks = row.get("recent_tasks") or []


def best_employee(db: Session, skill: str | None, snap=None):
    """Top allocation choice among AVAILABLE workers (fewest open tasks)."""
    from backend.services.matcher import skills_of
    snap = snap or _Snap(db)
    cands = []
    for e in snap.employees:
        if (e.status or "ACTIVE").upper() != "ACTIVE":
            continue
        if (e.availability or "AVAILABLE").upper() != "AVAILABLE":
            continue
        if skill:
            sk = skills_of(e)
            if not any(skill.strip().lower() in s or s in skill.strip().lower() for s in sk):
                continue
        cands.append((snap.counts.get(e.id, 0), e.name or "", e))
    if not cands:
        return None
    cands.sort(key=lambda x: (x[0], x[1]))
    return cands[0][2]


def best_machine(db: Session, skill: str | None, snap=None, exclude_busy=True):
    """Rule-based best fit: type-word overlap with the skill first, then
    GOOD health; always OPERATIONAL, no OPEN incident, optionally not busy."""
    snap = snap or _Snap(db)
    words = set((skill or "").lower().split())
    scored = []
    for m in snap.machines:
        if (m.status or "OPERATIONAL").upper() != "OPERATIONAL":
            continue
        if m.id in snap.open_inc:
            continue
        if exclude_busy and m.id in snap.busy:
            continue
        mtype = (m.machine_type or "").lower()
        overlap = 1 if words and any(w in mtype or mtype in w for w in words if len(w) > 2) else 0
        good = 0 if (m.health_status or "").upper() == "GOOD" else 1
        scored.append((-overlap, good, m.name or "", m))
    if not scored:
        return None
    scored.sort(key=lambda s: (s[0], s[1], s[2]))
    return scored[0][3]


def worker_ok(emp: Employee) -> bool:
    return (emp.status or "ACTIVE").upper() == "ACTIVE" and \
        (emp.availability or "AVAILABLE").upper() == "AVAILABLE"


def _resolve_or_409(db: Session, kind: str, ref, what: str):
    """Returns match dict. Raises 409 {question, options} when ambiguous,
    404-style 422 when unresolvable."""
    if ref is None or (isinstance(ref, str) and not ref.strip()):
        return None
    uid = _parse_uuid(ref)
    if uid is not None:
        model = {"task": Task, "order": Order, "employee": Employee,
                 "machine": Machine, "plan": WorkPlan}[kind]
        row = db.query(model).filter(model.id == uid).first()
        if row is None:
            raise HTTPException(status_code=422, detail=f"Unknown {what}.")
        label = getattr(row, "name", None) or getattr(row, "title", None) \
            or getattr(row, "order_number", None) or what
        return {"id": str(row.id), "label": label, "summary": label}
    match, ambiguous = resolve_one(db, kind, str(ref))
    if match is None:
        raise HTTPException(status_code=422, detail=f"Could not find {what} '{ref}'.")
    if ambiguous:
        # Re-fetch options for the question (resolve caps at 8; ask ≤3).
        from backend.services.resolve import resolve
        opts = [m["label"] for m in resolve(db, kind, str(ref))["matches"][:3]]
        raise HTTPException(status_code=409, detail={
            "question": f"Which {what}?", "options": opts})
    return match


def _need(question: str, options: list | None = None):
    return {"command_id": None, "summary": "", "warnings": [],
            "undo_available": False, "proposal_id": None, "created": {},
            "needs_question": {"question": question, "options": options or []}}


# ---------- autonomy (factory_profile JSON, no schema change) ----------

_AUTONOMY_CACHE = {"value": None, "at": 0.0}
_AUTONOMY_TTL = 5.0  # seconds; keeps a command from re-reading the profile


def get_autonomy(db: Session) -> str:
    import time as _time
    now = _time.monotonic()
    cached = _AUTONOMY_CACHE.get("value")
    if cached is not None and (now - _AUTONOMY_CACHE["at"]) < _AUTONOMY_TTL:
        return cached
    mode = "FAST"
    try:
        from backend.models.models import FactoryProfile
        prof = (db.query(FactoryProfile)
                .filter(FactoryProfile.status == "APPROVED")
                .order_by(FactoryProfile.updated_at.desc()).first())
        if prof is not None and isinstance(prof.profile, dict):
            m = (prof.profile.get("ai_preferences") or {}).get("autonomy", "FAST")
            mode = "ASK" if str(m).upper() == "ASK" else "FAST"
    except Exception:
        pass
    _AUTONOMY_CACHE["value"] = mode
    _AUTONOMY_CACHE["at"] = now
    return mode


def set_autonomy(db: Session, mode: str) -> str:
    mode = "ASK" if str(mode or "").upper() == "ASK" else "FAST"
    from backend.models.models import FactoryProfile
    prof = db.query(FactoryProfile).filter(
        FactoryProfile.status == "APPROVED").order_by(
        FactoryProfile.updated_at.desc()).first()
    if prof is None:
        prof = db.query(FactoryProfile).order_by(
            FactoryProfile.updated_at.desc()).first()
    if prof is None:
        raise HTTPException(status_code=404, detail="No factory profile yet.")
    profile = dict(prof.profile or {})
    prefs = dict(profile.get("ai_preferences") or {})
    prefs["autonomy"] = mode
    profile["ai_preferences"] = prefs
    prof.profile = profile
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(prof, "profile")
    db.commit()
    _AUTONOMY_CACHE["value"] = mode
    import time as _time
    _AUTONOMY_CACHE["at"] = _time.monotonic()
    return mode


# ---------- memory (audit + undo log) ----------

def _log(db: Session, *, action: str, summary: str, params: dict,
         created: dict, previous: dict | list | None, source: str,
         autonomy: str, warnings: list, task_id=None, order_id=None,
         machine_id=None, maintenance_id=None, extra: dict | None = None):
    # id is client-generated and the caller commits once after setting the
    # final title, so no flush/commit round trips happen here.
    mem = FactoryMemory(
        id=uuid4(),
        title=summary[:255],
        event_type="VOICE_COMMAND",
        description="; ".join(warnings)[:2000] if warnings else None,
        task_id=task_id, order_id=order_id, machine_id=machine_id,
        metadata_={**(extra or {}), "action": action, "params": params,
                   "created": created, "previous": previous,
                   "source": source, "autonomy": autonomy,
                   "warnings": warnings, "undone": False,
                   "maintenance_id": maintenance_id},
    )
    db.add(mem)
    return mem


def _undoable(mem: FactoryMemory, now=None):
    now = now or _now()
    if mem is None or mem.event_type != "VOICE_COMMAND":
        return False
    meta = mem.metadata_ or {}
    if meta.get("undone"):
        return False
    if meta.get("action") == "undo":
        return False
    try:
        age = (now - mem.created_at).total_seconds() if mem.created_at else 10 ** 9
    except Exception:
        return False
    return age <= pol.UNDO_MINUTES * 60


# ---------- the operations ----------

def _extract_spans(snap: _Snap, text: str) -> dict:
    """Pull explicit entity mentions straight out of command wording so a
    bare text call still resolves: full employee names, M-000 codes (or
    full machine names) and ORD-000 numbers. Longest names first."""
    t = text or ""
    found: dict = {}
    for e in sorted(snap.employees, key=lambda x: -len(x.name or "")):
        if e.name and re.search(rf"\b{re.escape(e.name)}\b", t, re.IGNORECASE):
            found["employee"] = e
            break
    if "employee" not in found:
        # EMP-004 spoken/typed code via the worker_credentials map.
        ce = re.search(r"\bEMP-?(\d{1,4})\b", t, re.IGNORECASE)
        if ce:
            want = f"EMP-{ce.group(1).zfill(3)}"
            by_code = {str(code).upper(): emp
                       for emp in snap.employees
                       for code in [snap.codes.get(emp.id)] if code}
            if by_code.get(want.upper()) is not None:
                found["employee"] = by_code[want.upper()]
    m = re.search(r"\bM-?(\d{1,4})\b", t, re.IGNORECASE)
    if m:
        code = f"M-{m.group(1).zfill(3)}"
        for mc in snap.machines:
            if (mc.name or "").upper().startswith(code):
                found["machine"] = mc
                break
    return found


# ---- task-name cleaning (spoken command -> clean name) ----
_PERSON_ROLE = r"(?:person|worker|employee|operator|welder|machinist|technician|fitter|one|guy)"
_SELECTION_RE = re.compile(
    r"\b(?:the\s+best(?:\s+available)?|best(?:\s+available)?|any\s+available"
    r"|anyone(?:\s+available)?|anybody(?:\s+available)?|any"
    r"|whoever(?:\s+is\s+available)?|you\s+decide|by\s+yourself|yourself|available)"
    rf"(?:\s+{_PERSON_ROLE})?\b",
    re.IGNORECASE,
)
_VERB_RE = re.compile(
    r"^(?:please\s+)?(?:assign|create|make|add|schedule|start|do|log|give|set|"
    r"plan|put|open|raise|file|book)\s+(?:(?:another|an|new|the|a)\s+)?",
    re.IGNORECASE,
)
_ARTICLE_TASK_RE = re.compile(r"\b(?:a|an|the|new|another)\s+(?:new\s+)?task\b", re.IGNORECASE)
_NEW_TASK_RE = re.compile(r"\b(?:new|another)\s+task\b", re.IGNORECASE)
_PRIORITY_WORD_RE = re.compile(r"\b(?:urgent|high|low|priority|please)\b", re.IGNORECASE)
_DEADLINE_PHRASE_RE = re.compile(
    r"\b(?:by|for|due|on|before|at|to)\s+(?:tomorrow|tonight|today|eod|end\s+of\s+day"
    r"|monday|tuesday|wednesday|thursday|friday|saturday|sunday"
    r"|\d{1,2}(?::\d{2})?\s*(?:am|pm)|in\s+\d+\s+(?:day|days|week|weeks))\b",
    re.IGNORECASE,
)
_BARE_TIME_RE = re.compile(r"\b(?:tomorrow|tonight|today|eod|end\s+of\s+day)\b", re.IGNORECASE)
_TRAILING_FILLER_RE = re.compile(
    r"\s+(?:to|for|by|on|due|from|with|at|of|the|a|an)\s*$", re.IGNORECASE)
_LEADING_PREP_RE = re.compile(r"^(?:to|for|by|on|at|of|with)\s+", re.IGNORECASE)
_TRAIL_TASKWORD_RE = re.compile(r"\s+(?:task|job|work|activity)s?$", re.IGNORECASE)
_LEADING_ARTICLE_RE = re.compile(r"^(?:a|an|the|new|another)\s+", re.IGNORECASE)
_CALLED_RE = re.compile(r"\b(?:called|named|titled)\s+(.+)$", re.IGNORECASE)
_CODE_RE = re.compile(r"\b(?:EMP|M|ORD)-?\d{1,4}\b", re.IGNORECASE)


def _clean_task_name(s: str) -> str:
    """Trim filler words, selection leftovers, priority words, deadline
    phrases and stray punctuation. Case is preserved (CNC stays CNC)."""
    s = re.sub(r"\s+", " ", (s or "").strip())
    s = s.strip(" \t\r\n.,;:!?\"'")
    s = _PRIORITY_WORD_RE.sub(" ", s)
    s = _DEADLINE_PHRASE_RE.sub(" ", s)
    s = _BARE_TIME_RE.sub(" ", s)
    s = _ARTICLE_TASK_RE.sub(" ", s)
    s = _NEW_TASK_RE.sub(" ", s)
    s = _LEADING_PREP_RE.sub("", s)
    s = _LEADING_ARTICLE_RE.sub("", s)
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"\s+", " ", s).strip()
        s = _TRAILING_FILLER_RE.sub("", s)
        s = _TRAIL_TASKWORD_RE.sub("", s)
        s = s.strip(" \t\r\n.,;:!?\"'")
    return s


def _task_name_from_command(text: str, spans: dict, skill: str | None = None) -> str:
    """Spoken command -> a clean task name.

    An explicit "called/named/titled X" phrase wins. Otherwise entity names,
    entity codes, selection phrases (best/any/available/you decide), priority
    words and deadline phrases are removed, then filler "task" wording and
    punctuation. Falls back to the matched skill, then "General task".
    """
    t = re.sub(r"\s+", " ", (text or "").strip())

    m = _CALLED_RE.search(t)
    if m:
        cand = _clean_task_name(m.group(1))
        if cand:
            return cand[:255]

    for ent in ("employee", "machine", "order"):
        row = spans.get(ent)
        if row is None:
            continue
        label = row.order_number if ent == "order" else row.name
        if label:
            t = re.sub(rf"\b{re.escape(str(label))}\b", " ", t, flags=re.IGNORECASE)

    t = _CODE_RE.sub(" ", t)
    t = _SELECTION_RE.sub(" ", t)
    t = _PRIORITY_WORD_RE.sub(" ", t)
    t = _DEADLINE_PHRASE_RE.sub(" ", t)
    t = _BARE_TIME_RE.sub(" ", t)
    t = _ARTICLE_TASK_RE.sub(" ", t)
    t = _NEW_TASK_RE.sub(" ", t)
    t = _VERB_RE.sub("", t)
    t = _LEADING_PREP_RE.sub("", t)

    cand = _clean_task_name(t)
    if not cand and skill:
        cand = _clean_task_name(skill)
    return (cand or "General task")[:255]


def _employee_line(db: Session, emp, codes=None) -> str:
    if emp is None:
        return "unassigned"
    if codes is None:
        from backend.services.resolve import employee_code_map
        codes = employee_code_map(db)
    code = codes.get(emp.id)
    return f"{emp.name} ({code})" if code else emp.name


def run_create_task(db: Session, *, text: str, employee_ref=None, employee_id=None,
                    machine_ref=None, machine_id=None, order_ref=None, order_id=None,
                    priority=None, deadline_text=None, description=None,
                    autopilot=False, source="voice", explicit_deadline=None):
    warnings = []
    snap = _Snap(db)
    spans = _extract_spans(snap, text)
    o = re.search(r"\bORD-?(\d+)\b", text or "", re.IGNORECASE)
    if o and "order" not in spans:
        num = f"ORD-{o.group(1).zfill(3)}"
        row = db.query(Order).filter(Order.order_number == num).first()
        if row is not None:
            spans["order"] = row
    skill = pol.match_skill(text, snap.skills)
    name = _task_name_from_command(text, spans, skill)

    emp = None
    if employee_id is not None or employee_ref:
        if employee_id is not None:
            uid = _parse_uuid(employee_id)
            emp = db.query(Employee).filter(Employee.id == uid).first() if uid else None
            if emp is None:
                raise HTTPException(status_code=422, detail="Unknown employee.")
        else:
            m = _resolve_or_409(db, "employee", employee_ref, "worker")
            emp = db.query(Employee).filter(Employee.id == UUID(m["id"])).first()
        if not worker_ok(emp):
            if not autopilot:
                return _need(f"{emp.name} is {emp.availability or emp.status}. Assign anyway?",
                            ["Yes", "No"])
            alt = best_employee(db, skill, snap)
            warnings.append(f"{emp.name} is unavailable; chose {alt.name if alt else 'nobody'} instead")
            emp = alt
    elif spans.get("employee") is not None:
        emp = spans["employee"]
        if not worker_ok(emp):
            if not autopilot:
                return _need(f"{emp.name} is {emp.availability or emp.status}. Assign anyway?",
                            ["Yes", "No"])
            alt = best_employee(db, skill, snap)
            warnings.append(f"{emp.name} is unavailable; chose {alt.name if alt else 'nobody'} instead")
            emp = alt
    elif autopilot or _wants_best(text):
        emp = best_employee(db, skill, snap)
        if emp is None:
            warnings.append("no available worker found; task left unassigned")

    mac = None
    if spans.get("machine") is not None and machine_id is None and not machine_ref:
        mac = spans["machine"]
        if mac.id in snap.open_inc:
            if not autopilot:
                return _need(f"Machine {mac.name} has an OPEN incident. Use it anyway?",
                            ["Yes", "No"])
            alt = best_machine(db, skill, snap)
            warnings.append(f"{mac.name} has an OPEN incident; chose {alt.name if alt else 'no machine'} instead")
            mac = alt
    if mac is None and (machine_id is not None or machine_ref):
        if machine_id is not None:
            uid = _parse_uuid(machine_id)
            mac = db.query(Machine).filter(Machine.id == uid).first() if uid else None
            if mac is None:
                raise HTTPException(status_code=422, detail="Unknown machine.")
        else:
            m = _resolve_or_409(db, "machine", machine_ref, "machine")
            mac = db.query(Machine).filter(Machine.id == UUID(m["id"])).first()
        if mac.id in snap.open_inc:
            if not autopilot:
                return _need(f"Machine {mac.name} has an OPEN incident. Use it anyway?",
                            ["Yes", "No"])
            alt = best_machine(db, skill, snap)
            warnings.append(f"{mac.name} has an OPEN incident; chose {alt.name if alt else 'no machine'} instead")
            mac = alt
    if mac is None:
        mac = best_machine(db, skill, snap)
        if mac is None:
            warnings.append("no healthy free machine found")

    order = None
    if spans.get("order") is not None and order_id is None and not order_ref:
        order = spans["order"]
    if order is None and (order_id is not None or order_ref):
        if order_id is not None:
            uid = _parse_uuid(order_id)
            order = db.query(Order).filter(Order.id == uid).first() if uid else None
            if order is None:
                raise HTTPException(status_code=422, detail="Unknown order.")
        else:
            m = _resolve_or_409(db, "order", order_ref, "order")
            order = db.query(Order).filter(Order.id == UUID(m["id"])).first()
    if order is None:
        warnings.append("no order linked")

    prio = (priority or "").upper() or None
    if prio not in ("LOW", "NORMAL", "HIGH", "URGENT"):
        prio = pol.parse_priority(text)

    if explicit_deadline:
        try:
            dl = datetime.fromisoformat(str(explicit_deadline).replace("Z", "+00:00"))
            dl = dl if dl.tzinfo else dl.replace(tzinfo=pol.IST)
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="Bad deadline (ISO datetime required).")
    elif order is not None and order.deadline is not None:
        dl = order.deadline
        if dl.tzinfo is None:
            dl = dl.replace(tzinfo=pol.IST)
    else:
        dl = pol.parse_deadline(deadline_text or text)

    # Duplicate guard: same name + worker + order within 60 s. The recent
    # rows already came back with the snapshot (no extra round trip).
    since = _now() - timedelta(seconds=pol.DUPLICATE_SECONDS)

    def _recent_match(rt):
        if (rt.get("name") or "") != name:
            return False
        if (rt.get("employee_id") or None) != (str(emp.id) if emp else None):
            return False
        if (rt.get("order_id") or None) != (str(order.id) if order else None):
            return False
        try:
            created = datetime.fromisoformat(str(rt.get("created_at")).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return False
        return created >= since

    dup = next((rt for rt in snap.recent_tasks if _recent_match(rt)), None)
    if dup is not None:
        who = _employee_line(db, emp, snap.codes)
        return {"command_id": None, "summary": f"Already done: {name} for {who}.",
                "warnings": ["created just now; reusing it instead of duplicating"],
                "undo_available": False, "proposal_id": None, "created": {},
                "needs_question": None}

    desc = (description or f"{name} — requested by admin"
            + (f" for {emp.name}" if emp else "")
            + (f", due {pol.speak_due(dl)}" if dl else ""))[:2000]
    t = Task(id=uuid4(), name=name[:255], description=desc, required_skill=skill,
             priority=prio, status="PENDING", progress=0.0,
             employee_id=emp.id if emp else None,
             machine_id=mac.id if mac else None,
             order_id=order.id if order else None, deadline=dl)
    db.add(t)  # id set explicitly; no flush round trip needed before commit
    created = {"task_id": str(t.id)}
    mem = _log(db, action="create_task",
               summary="",  # filled below
               params={"text": text, "skill": skill, "priority": prio,
                       "deadline": _iso(dl)},
               created=created, previous=None, source=source,
               autonomy="autopilot" if autopilot else "fast",
               warnings=warnings, task_id=t.id,
               order_id=order.id if order else None,
               machine_id=mac.id if mac else None)
    who = _employee_line(db, emp, snap.codes)
    parts = f"Done: {name} task assigned to {who}"
    if mac is not None:
        parts += f" on {mac.name.split(' ')[0]}"
    parts += f", due {pol.speak_due(dl)}."
    if warnings:
        parts += " Note: " + "; ".join(warnings) + "."
    mem.title = parts[:255]
    db.commit()
    return {"command_id": str(mem.id), "summary": parts, "warnings": warnings,
            "undo_available": True, "proposal_id": None,
            "created": {**created, "task_id": str(t.id),
                        "employee_id": str(emp.id) if emp else None,
                        "machine_id": str(mac.id) if mac else None,
                        "order_id": str(order.id) if order else None},
            "needs_question": None}


def _wants_best(text: str) -> bool:
    return bool(re.search(r"\bbest\b|\banyone\b|\banybody\b|\byou decide\b|\byourself\b", (text or "").lower()))


def run_create_order(db: Session, *, product: str, quantity: int = 0,
                     customer: str | None = None, autopilot=False, source="voice"):
    warnings = []
    existing = [o.order_number for o in db.query(Order).all()]
    number = pol.next_order_number(existing)
    while db.query(Order).filter(Order.order_number == number).first() is not None:
        number = pol.next_order_number(existing + [number])
        existing.append(number)
    try:
        qty = max(0, int(quantity or 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Quantity must be a number.")
    o = Order(order_number=number, product=(product or "General").strip()[:255] or "General",
              customer_name=(customer or "").strip()[:255] or None,
              quantity=qty, status="PENDING", priority="NORMAL", progress=0.0)
    db.add(o)
    db.flush()
    mem = _log(db, action="create_order", summary="",
               params={"product": o.product, "quantity": qty, "customer": o.customer_name},
               created={"order_id": str(o.id)}, previous=None, source=source,
               autonomy="autopilot" if autopilot else "fast",
               warnings=warnings, order_id=o.id)
    parts = f"Done: order {number} for {qty} {o.product} created."
    mem.title = parts[:255]
    db.commit()
    return {"command_id": str(mem.id), "summary": parts, "warnings": warnings,
            "undo_available": True, "proposal_id": None,
            "created": {"order_id": str(o.id), "order_number": o.order_number},
            "needs_question": None}


def _apply_assign(db: Session, t: Task, emp, mac, prev: dict):
    if emp is not None:
        prev.setdefault(str(t.id), {}).setdefault("employee_id",
            str(t.employee_id) if t.employee_id else None)
        t.employee_id = emp.id
    if mac is not None:
        prev.setdefault(str(t.id), {}).setdefault("machine_id",
            str(t.machine_id) if t.machine_id else None)
        t.machine_id = mac.id


def run_assign(db: Session, *, task_ref=None, task_id=None, task_ids=None,
               employee_ref=None, employee_id=None, machine_ref=None, machine_id=None,
               autopilot=False, source="voice", confirmed=False):
    warnings = []
    tids = []
    if task_ids:
        for v in task_ids:
            uid = _parse_uuid(v)
            if uid is None:
                raise HTTPException(status_code=422, detail="Bad task id in batch.")
            tids.append(uid)
    elif task_id is not None or task_ref:
        if task_id is not None:
            uid = _parse_uuid(task_id)
            t = db.query(Task).filter(Task.id == uid).first() if uid else None
            if t is None:
                raise HTTPException(status_code=422, detail="Unknown task.")
            tids = [t.id]
        else:
            m = _resolve_or_409(db, "task", task_ref, "task")
            tids = [UUID(m["id"])]
    else:
        # Batch autopilot over unassigned tasks.
        cand = db.query(Task).filter(Task.employee_id.is_(None),
                                     ~Task.status.in_(list(DONE_TASK))).all()
        limit = pol.AUTOPILOT_MAX_AFFECTED if autopilot else pol.TIER2_MAX_AFFECTED
        if len(cand) > limit and not autopilot:
            return _need(f"This would assign {len(cand)} tasks. Go ahead with all of them?",
                        ["Yes", "No"])
        if len(cand) > pol.AUTOPILOT_MAX_AFFECTED:
            return _need(f"This would assign {len(cand)} tasks — over the limit of "
                         f"{pol.AUTOPILOT_MAX_AFFECTED}. Narrow it down?",
                        ["Yes", "No"])
        tids = [t.id for t in cand]
        if not tids:
            return {"command_id": None, "summary": "Nothing to assign: no unassigned open tasks.",
                    "warnings": [], "undo_available": False, "proposal_id": None,
                    "created": {}, "needs_question": None}
        warnings.append(f"batch of {len(tids)} tasks as one undoable batch")
    if len(tids) > pol.TIER2_MAX_AFFECTED and not autopilot and not confirmed:
        return _need(f"This would assign {len(tids)} tasks. Go ahead with all of them?",
                    ["Yes", "No"])
    if len(tids) > pol.AUTOPILOT_MAX_AFFECTED:
        raise HTTPException(status_code=422, detail="Batch over the limit of "
                            f"{pol.AUTOPILOT_MAX_AFFECTED} tasks.")

    emp = None
    if employee_id is not None or employee_ref:
        if employee_id is not None:
            uid = _parse_uuid(employee_id)
            emp = db.query(Employee).filter(Employee.id == uid).first() if uid else None
            if emp is None:
                raise HTTPException(status_code=422, detail="Unknown employee.")
        else:
            m = _resolve_or_409(db, "employee", employee_ref, "worker")
            emp = db.query(Employee).filter(Employee.id == UUID(m["id"])).first()
        if not worker_ok(emp):
            if not (autopilot or confirmed):
                return _need(f"{emp.name} is {emp.availability or emp.status}. Assign anyway?",
                            ["Yes", "No"])
            from backend.services.smart_split import candidates_for
            skill = (db.query(Task).filter(Task.id == tids[0]).first().required_skill
                     if tids else None)
            alt = best_employee(db, skill)
            warnings.append(f"{emp.name} is unavailable; chose {alt.name if alt else 'nobody'} instead")
            emp = alt
    else:
        skill = db.query(Task).filter(Task.id == tids[0]).first().required_skill if tids else None
        emp = best_employee(db, skill)
        if emp is None:
            raise HTTPException(status_code=422, detail="No available worker found.")
        if len(tids) == 1:
            warnings.append(f"picked {_employee_line(db, emp)} (fewest open tasks)")

    mac = None
    if machine_id is not None or machine_ref:
        if machine_id is not None:
            uid = _parse_uuid(machine_id)
            mac = db.query(Machine).filter(Machine.id == uid).first() if uid else None
            if mac is None:
                raise HTTPException(status_code=422, detail="Unknown machine.")
        else:
            m = _resolve_or_409(db, "machine", machine_ref, "machine")
            mac = db.query(Machine).filter(Machine.id == UUID(m["id"])).first()
        if mac.id in _open_incident_machines(db) and not (autopilot or confirmed):
            return _need(f"Machine {mac.name} has an OPEN incident. Use it anyway?",
                        ["Yes", "No"])

    prev = {}
    names = []
    for tid in tids:
        t = db.query(Task).filter(Task.id == tid).first()
        if t is None:
            continue
        _apply_assign(db, t, emp, mac, prev)
        names.append(t.name)
    if not names:
        raise HTTPException(status_code=404, detail="No tasks found.")
    who = _employee_line(db, emp, None)
    if len(names) == 1:
        parts = f"Done: {names[0]} assigned to {who}."
    else:
        parts = f"Done: {len(names)} tasks assigned to {who} in one batch."
    if warnings:
        parts += " Note: " + "; ".join(warnings) + "."
    mem = _log(db, action="assign_batch" if len(names) > 1 else "assign",
               summary="", params={"task_ids": [str(t) for t in tids]},
               created={}, previous=prev, source=source,
               autonomy="autopilot" if autopilot else "fast",
               warnings=warnings,
               task_id=tids[0] if len(tids) == 1 else None)
    mem.title = parts[:255]
    db.commit()
    return {"command_id": str(mem.id), "summary": parts, "warnings": warnings,
            "undo_available": True, "proposal_id": None,
            "created": {"task_ids": [str(x) for x in tids],
                        "employee_id": str(emp.id) if emp else None,
                        "machine_id": str(mac.id) if mac else None},
            "needs_question": None}


def run_change(db: Session, *, task_ref=None, task_id=None, employee_ref=None,
               employee_id=None, machine_ref=None, machine_id=None,
               deadline_text=None, explicit_deadline=None, priority=None,
               status=None, autopilot=False, source="voice", confirmed=False):
    warnings = []
    if task_id is not None:
        uid = _parse_uuid(task_id)
        t = db.query(Task).filter(Task.id == uid).first() if uid else None
        if t is None:
            raise HTTPException(status_code=422, detail="Unknown task.")
    else:
        m = _resolve_or_409(db, "task", task_ref, "task")
        t = db.query(Task).filter(Task.id == UUID(m["id"])).first()
    prev = {str(t.id): {"employee_id": str(t.employee_id) if t.employee_id else None,
                        "machine_id": str(t.machine_id) if t.machine_id else None,
                        "deadline": _iso(t.deadline), "priority": t.priority,
                        "status": t.status}}
    bits = []
    if employee_id is not None or employee_ref:
        if employee_id is not None:
            uid = _parse_uuid(employee_id)
            emp = db.query(Employee).filter(Employee.id == uid).first() if uid else None
            if emp is None:
                raise HTTPException(status_code=422, detail="Unknown employee.")
        else:
            m = _resolve_or_409(db, "employee", employee_ref, "worker")
            emp = db.query(Employee).filter(Employee.id == UUID(m["id"])).first()
        if not worker_ok(emp) and not (autopilot or confirmed):
            return _need(f"{emp.name} is {emp.availability or emp.status}. Assign anyway?",
                        ["Yes", "No"])
        t.employee_id = emp.id
        bits.append(f"assigned to {emp.name}")
    if machine_id is not None or machine_ref:
        if machine_id is not None:
            uid = _parse_uuid(machine_id)
            mac = db.query(Machine).filter(Machine.id == uid).first() if uid else None
            if mac is None:
                raise HTTPException(status_code=422, detail="Unknown machine.")
        else:
            m = _resolve_or_409(db, "machine", machine_ref, "machine")
            mac = db.query(Machine).filter(Machine.id == UUID(m["id"])).first()
        if mac.id in _open_incident_machines(db) and not (autopilot or confirmed):
            return _need(f"Machine {mac.name} has an OPEN incident. Use it anyway?",
                        ["Yes", "No"])
        t.machine_id = mac.id
        bits.append(f"moved to {mac.name.split(' ')[0]}")
    if explicit_deadline or deadline_text:
        if (t.status or "").upper() == "IN_PROGRESS" and not (autopilot or confirmed):
            return _need(f"{t.name} is already IN PROGRESS. Move its deadline anyway?",
                        ["Yes", "No"])
        if explicit_deadline:
            try:
                dl = datetime.fromisoformat(str(explicit_deadline).replace("Z", "+00:00"))
                dl = dl if dl.tzinfo else dl.replace(tzinfo=pol.IST)
            except (ValueError, TypeError):
                raise HTTPException(status_code=422, detail="Bad deadline (ISO datetime required).")
        else:
            dl = pol.parse_deadline(deadline_text)
        t.deadline = dl
        bits.append(f"due {pol.speak_due(dl)}")
        if (t.status or "").upper() == "IN_PROGRESS":
            warnings.append("deadline moved on an IN_PROGRESS task")
    if priority:
        p = priority.upper()
        if p not in ("LOW", "NORMAL", "HIGH", "URGENT"):
            raise HTTPException(status_code=422, detail="Priority must be LOW, NORMAL, HIGH or URGENT.")
        t.priority = p
        bits.append(f"priority {p}")
    if status:
        s = status.upper()
        if s in ("STARTED", "IN_PROGRESS"):
            s = "IN_PROGRESS"
        if s in ("COMPLETED", "DONE"):
            s = "COMPLETED"
        if s not in ("PENDING", "IN_PROGRESS", "COMPLETED", "DONE", "CANCELLED"):
            raise HTTPException(status_code=422, detail="Unknown status.")
        if t.status != s:
            if s == "IN_PROGRESS" and t.start_time is None:
                from datetime import datetime as _dt, timezone as _tz
                t.start_time = _dt.now(_tz.utc)
            if s in ("COMPLETED", "DONE"):
                t.progress = 1.0
            t.status = s
            bits.append("marked started" if s == "IN_PROGRESS" else
                        "marked completed" if s in ("COMPLETED", "DONE") else f"set to {s}")
    if not bits:
        raise HTTPException(status_code=422, detail="Nothing to change.")
    parts = f"Done: {t.name} — " + ", ".join(bits) + "."
    if warnings:
        parts += " Note: " + "; ".join(warnings) + "."
    mem = _log(db, action="change", summary="", params={"task_id": str(t.id)},
               created={}, previous=prev, source=source,
               autonomy="autopilot" if autopilot else "fast",
               warnings=warnings, task_id=t.id,
               order_id=t.order_id, machine_id=t.machine_id)
    mem.title = parts[:255]
    db.commit()
    return {"command_id": str(mem.id), "summary": parts, "warnings": warnings,
            "undo_available": True, "proposal_id": None,
            "created": {"task_id": str(t.id)}, "needs_question": None}


def run_maintenance(db: Session, *, machine_ref=None, machine_id=None,
                    issue=None, autopilot=False, source="voice"):
    warnings = []
    if machine_id is not None:
        uid = _parse_uuid(machine_id)
        mac = db.query(Machine).filter(Machine.id == uid).first() if uid else None
        if mac is None:
            raise HTTPException(status_code=422, detail="Unknown machine.")
    else:
        m = _resolve_or_409(db, "machine", machine_ref, "machine")
        mac = db.query(Machine).filter(Machine.id == UUID(m["id"])).first()
    text = str(issue or "Voice-requested check")[:200]
    mnt = Maintenance(id=uuid4(), machine_id=mac.id, issue=text,
                      description="Direct voice command", status="PENDING")
    db.add(mnt)
    mem = _log(db, action="schedule_maintenance", summary="",
               params={"machine_id": str(mac.id), "issue": text},
               created={"maintenance_id": str(mnt.id)}, previous=None,
               source=source, autonomy="autopilot" if autopilot else "fast",
               warnings=warnings, machine_id=mac.id)
    parts = f"Done: maintenance scheduled for {mac.name.split(' ')[0]} — {text}."
    mem.title = parts[:255]
    db.commit()
    return {"command_id": str(mem.id), "summary": parts, "warnings": warnings,
            "undo_available": True, "proposal_id": None,
            "created": {"maintenance_id": str(mnt.id), "machine_id": str(mac.id)},
            "needs_question": None}


# ---------- ASK mode: same resolved params become proposals ----------

def propose_instead(db: Session, *, action_type: str, params: dict, reason: str):
    from uuid import uuid4 as _uuid4
    eid = params.get("task_id") or params.get("machine_id") or params.get("order_id")
    row = AIRecommendation(
        recommendation_type=action_type, entity_type="PROPOSAL",
        entity_id=UUID(str(eid)) if eid else _uuid4(),
        recommendation={"DRAFT_ASSIGNMENT": "Create task"}.get(
            action_type, action_type.replace("_", " ").title()),
        reason=(reason or "")[:2000] or None,
        confidence=None, status="PENDING")
    row.params = params
    db.add(row)
    db.flush()
    mem = _log(db, action="propose", summary="",
               params={"action_type": action_type, **params},
               created={"proposal_id": str(row.id)}, previous=None,
               source="assistant", autonomy="ask", warnings=[],
               task_id=_parse_uuid(params.get("task_id")),
               order_id=_parse_uuid(params.get("order_id")),
               machine_id=_parse_uuid(params.get("machine_id")))
    label = {"DRAFT_ASSIGNMENT": "Create task"}.get(action_type,
              action_type.replace("_", " ").title())
    parts = f"Proposed: {label} is waiting for approval on screen."
    mem.title = parts[:255]
    db.commit()
    return {"command_id": str(mem.id), "summary": parts, "warnings": [],
            "undo_available": False, "proposal_id": str(row.id),
            "created": {"proposal_id": str(row.id)}, "needs_question": None}


# ---------- undo + recent ----------

def undo_command(db: Session, command_id: str):
    uid = _parse_uuid(command_id)
    mem = db.query(FactoryMemory).filter(FactoryMemory.id == uid).first() \
        if uid else None
    if mem is None or mem.event_type != "VOICE_COMMAND":
        raise HTTPException(status_code=404, detail="Command not found.")
    meta = dict(mem.metadata_ or {})
    if meta.get("undone"):
        return {"undone": True, "summary": "Already undone.", "command_id": str(mem.id)}
    if not _undoable(mem):
        raise HTTPException(status_code=409, detail="Too late to undo — the 15 minute window passed.")
    created = meta.get("created") or {}
    previous = meta.get("previous") or {}
    action = meta.get("action")

    if action in ("create_task",):
        tid = _parse_uuid(created.get("task_id"))
        t = db.query(Task).filter(Task.id == tid).first() if tid else None
        if t is None:
            raise HTTPException(status_code=404, detail="Task already gone.")
        if (t.status or "PENDING").upper() != "PENDING" or \
                (t.updated_at and mem.created_at and t.updated_at > mem.created_at):
            raise HTTPException(status_code=409, detail="Cannot undo — the task was already started or updated.")
        db.delete(t)
    elif action == "create_order":
        oid = _parse_uuid(created.get("order_id"))
        o = db.query(Order).filter(Order.id == oid).first() if oid else None
        if o is None:
            raise HTTPException(status_code=404, detail="Order already gone.")
        linked = db.query(Task).filter(Task.order_id == o.id).count()
        if linked:
            raise HTTPException(status_code=409, detail="Cannot undo — tasks were already added to this order.")
        db.delete(o)
    elif action == "schedule_maintenance":
        mid = _parse_uuid(created.get("maintenance_id"))
        mnt = db.query(Maintenance).filter(Maintenance.id == mid).first() if mid else None
        if mnt is None:
            raise HTTPException(status_code=404, detail="Maintenance record already gone.")
        if (mnt.status or "PENDING").upper() != "PENDING":
            raise HTTPException(status_code=409, detail="Cannot undo — maintenance already started.")
        db.delete(mnt)
    elif action in ("assign", "assign_batch", "change"):
        # previous is {task_id: {employee_id, machine_id, deadline,
        # priority, status}} for all three (change stores a single entry).
        items = previous if isinstance(previous, dict) else {}
        for tid_s, prev in (items or {}).items():
            tid = _parse_uuid(tid_s)
            t = db.query(Task).filter(Task.id == tid).first() if tid else None
            if t is None or not isinstance(prev, dict):
                continue
            # Key presence (not None-ness): None is a real previous value
            # meaning "was unassigned / had no deadline".
            if "employee_id" in prev:
                t.employee_id = UUID(prev["employee_id"]) if prev["employee_id"] else None
            if "machine_id" in prev:
                t.machine_id = UUID(prev["machine_id"]) if prev["machine_id"] else None
            if "deadline" in prev:
                if prev["deadline"]:
                    try:
                        t.deadline = datetime.fromisoformat(str(prev["deadline"]).replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass
                else:
                    t.deadline = None
            if "priority" in prev and prev["priority"]:
                t.priority = prev["priority"]
            if "status" in prev and prev["status"]:
                t.status = prev["status"]
    elif action == "propose":
        pid = _parse_uuid((created or {}).get("proposal_id"))
        if pid:
            row = db.query(AIRecommendation).filter(AIRecommendation.id == pid).first()
            if row is not None and row.status == "PENDING":
                db.delete(row)
    else:
        raise HTTPException(status_code=409, detail="This command cannot be undone.")

    meta["undone"] = True
    mem.metadata_ = meta
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(mem, "metadata_")
    undo_mem = FactoryMemory(
        title=f"Undid: {(mem.title or '')[:110]}",
        event_type="VOICE_COMMAND",
        description=None, task_id=mem.task_id, order_id=mem.order_id,
        machine_id=mem.machine_id,
        metadata_={"action": "undo", "params": {}, "created": {},
                   "previous": None, "source": meta.get("source", "voice"),
                   "autonomy": meta.get("autonomy", "fast"), "warnings": [],
                   "undone": False, "undone_command_id": str(mem.id),
                   "maintenance_id": None},
    )
    db.add(undo_mem)
    db.commit()
    parts = f"Undone: {mem.title}."
    return {"undone": True, "summary": parts, "command_id": str(undo_mem.id)}


def recent_commands(db: Session, limit: int = 10):
    limit = max(1, min(50, int(limit or 10)))
    rows = db.query(FactoryMemory).filter(
        FactoryMemory.event_type == "VOICE_COMMAND").order_by(
        FactoryMemory.created_at.desc()).limit(limit).all()
    out = []
    for m in rows:
        meta = m.metadata_ or {}
        out.append({
            "command_id": str(m.id),
            "action": meta.get("action"),
            "summary": m.title,
            "at": _iso(m.created_at),
            "warnings": meta.get("warnings") or [],
            "undo_available": _undoable(m) and meta.get("action") != "undo",
            "proposal_id": (meta.get("created") or {}).get("proposal_id")
            if meta.get("action") == "propose" else None,
        })
    return out


def latest_undoable(db: Session):
    rows = db.query(FactoryMemory).filter(
        FactoryMemory.event_type == "VOICE_COMMAND").order_by(
        FactoryMemory.created_at.desc()).limit(25).all()
    for m in rows:
        meta = m.metadata_ or {}
        if meta.get("action") == "undo" or meta.get("undone"):
            continue
        if _undoable(m):
            return m
    return None
