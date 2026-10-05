"""Natural-reference resolver (Part 2+3). ONE shared implementation used by
GET /api/resolve, the voice agent (via REST) and the text assistant.

Matches full ids, exact/partial names (case-insensitive), order numbers,
machine codes/names (including spoken forms like "M 001" or
"M zero zero one"), skill + assignee combos ("welding task for Suresh"),
and employee codes/names ("EMP-001", "emp 001", "employee one").

Responses never contain email, username, password or hash — only names,
codes, statuses and other speakable facts. Raw ids are included for the
MODEL to pass back (never spoken; the agent instructions forbid it).
"""
import re
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.models.models import (
    AIRecommendation,
    Employee,
    Incident,
    Machine,
    Order,
    Task,
    WorkerCredential,
    WorkPlan,
)

TYPES = ("task", "order", "incident", "proposal", "employee", "machine", "plan")
MAX_MATCHES = 8

ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}
TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}


def words_to_digits(text: str) -> str:
    """Spoken digit runs to digits: "zero zero one" -> "001", "one" -> "1",
    "twenty one" -> "21". Unknown words pass through untouched."""
    out = []
    for tok in re.split(r"[\s\-]+", (text or "").strip().lower()):
        if not tok:
            continue
        if tok in ONES:
            out.append(str(ONES[tok]))
        elif tok in TENS:
            out.append(str(TENS[tok]))
        elif tok.isdigit():
            out.append(tok)
        else:
            out.append(tok)
    # Compose tens + ones ("twenty","one" -> "21").
    composed = []
    i = 0
    while i < len(out):
        if (out[i].isdigit() and int(out[i]) in TENS.values()
                and i + 1 < len(out) and out[i + 1].isdigit()
                and 1 <= int(out[i + 1]) <= 9 and len(out[i + 1]) == 1
                and len(out[i]) == 2):
            composed.append(str(int(out[i]) + int(out[i + 1])))
            i += 2
        else:
            composed.append(out[i])
            i += 1
    # Bare single digits concatenate ("zero","zero","one" -> "001").
    if composed and all(c.isdigit() and len(c) == 1 for c in composed):
        return "".join(composed)
    return " ".join(composed)


def _squash_spelled_letters(text: str, word: str) -> str:
    """Collapse "e m p ..." / "m ..." style spelling ("E M P one" -> "emp one")."""
    letters = r"\s*".join(word)
    return re.sub(rf"\b{letters}\b", word, (text or "").lower()).strip()


def normalize_machine_code(q: str):
    """"M-001", "M 001", "M001", "M zero zero one", "machine one" -> "M-001"."""
    if not q:
        return None
    t = _squash_spelled_letters(q, "m")
    t = re.sub(r"^machine\s+", "m ", t.strip().lower())
    t = words_to_digits(t).replace(" ", "")
    m = re.fullmatch(r"m-?(\d{1,4})", t)
    if m:
        return f"M-{m.group(1).zfill(3)}"
    return None


def normalize_employee_code(q: str):
    """"EMP-001", "emp 001", "EMP001", "emp-1", "E M P zero zero one",
    "employee one", "employee number 1" -> "EMP-001" (padded to 3 digits)."""
    if not q:
        return None
    t = _squash_spelled_letters(q, "emp")
    t = re.sub(r"^(employee|staff|worker)\s+", "", t.strip().lower())
    t = re.sub(r"^(number|no\.?|code|#)\s+", "", t)
    # Digits (as words or numerals) BEFORE spaces are removed, so
    # "zero zero two" still parses.
    t = words_to_digits(t)
    t2 = t.replace(" ", "")
    m = re.fullmatch(r"emp-?(\d{1,4})", t2)
    if m:
        return f"EMP-{m.group(1).zfill(3)}"
    # Bare number left after stripping ("employee one" -> "1").
    if re.fullmatch(r"\d{1,4}", t2):
        return f"EMP-{t2.zfill(3)}"
    return None


def try_uuid(q: str):
    try:
        return UUID(str(q).strip())
    except (ValueError, AttributeError):
        return None


def employee_code_map(db: Session) -> dict:
    """employee_id -> employee_code (codes only, never secrets)."""
    return {c.employee_id: c.employee_code for c in db.query(WorkerCredential).all()
            if c.employee_code}


def _open_task_count(db: Session, employee_id) -> int:
    return db.query(Task).filter(
        Task.employee_id == employee_id,
        Task.status.in_(["PENDING", "IN_PROGRESS", "PLANNED"])).count()


def _machine_code(name: str):
    m = re.match(r"^(M-\d{3})", (name or "").strip())
    return m.group(1) if m else None


def _ranked(exact: list, starts: list, partial: list, seen: set, limit=MAX_MATCHES):
    out = []
    for bucket in (exact, starts, partial):
        for m in bucket:
            if m["id"] not in seen:
                seen.add(m["id"])
                out.append(m)
                if len(out) >= limit:
                    return out
    return out


def _resolve_task(db: Session, q: str, codes: dict) -> list:
    q = (q or "").strip()
    if not q:
        return []
    uid = try_uuid(q)
    if uid:
        t = db.query(Task).filter(Task.id == uid).first()
        return [_task_match(db, t, codes)] if t else []
    # "welding task for Suresh" / "task for ORD-003".
    m = re.match(r"^(?P<skill>.+?)\s+tasks?\s+for\s+(?P<who>.+)$", q, re.IGNORECASE)
    skill_only = None
    who_only = None
    if m:
        skill_only = m.group("skill").strip()
        who_only = m.group("who").strip()
    else:
        m2 = re.match(r"^tasks?\s+for\s+(?P<who>.+)$", q, re.IGNORECASE)
        if m2:
            who_only = m2.group("who").strip()
    if skill_only or who_only:
        cands = db.query(Task).all()
        if skill_only and skill_only.lower() not in ("a", "the", "any"):
            cands = [t for t in cands if skill_only.lower() in (t.required_skill or "").lower()]
        if who_only:
            emp_hit = db.query(Employee).filter(Employee.name.ilike(f"%{who_only}%")).all()
            emp_ids = {e.id for e in emp_hit}
            by_order = [t for t in cands if t.order_id and (
                (db.query(Order).filter(Order.id == t.order_id).first() or _blank()).order_number or ""
            ).lower() == who_only.lower()]
            by_emp = [t for t in cands if t.employee_id in emp_ids]
            cands = by_emp + [t for t in by_order if t not in by_emp]
        return [_task_match(db, t, codes) for t in cands[:MAX_MATCHES]]
    if re.fullmatch(r"(?i)([a-z ]+)?tasks?", q):
        return []
    all_tasks = db.query(Task).all()
    ql = q.lower()
    exact = [_task_match(db, t, codes) for t in all_tasks if (t.name or "").lower() == ql]
    starts = [_task_match(db, t, codes) for t in all_tasks
              if (t.name or "").lower().startswith(ql)]
    partial = [_task_match(db, t, codes) for t in all_tasks if ql in (t.name or "").lower()]
    return _ranked(exact, starts, partial, set())


def _blank():
    class _B:
        order_number = ""
    return _B()


def _task_match(db: Session, t, codes: dict) -> dict:
    emp = db.query(Employee).filter(Employee.id == t.employee_id).first() \
        if t.employee_id else None
    mac = None
    if t.machine_id:
        mac = _machine_code((db.query(Machine).filter(
            Machine.id == t.machine_id).first() or _blank_machine()).name)
    order_no = None
    if t.order_id:
        o = db.query(Order).filter(Order.id == t.order_id).first()
        order_no = o.order_number if o else None
    who = f", assigned to {emp.name}" + \
        (f" ({codes.get(emp.id)})" if codes.get(emp.id) else "") if emp else ", unassigned"
    label = t.name or "Untitled task"
    return {
        "type": "task",
        "id": str(t.id),
        "label": label,
        "detail": t.status,
        "summary": (f"{label} — {t.status}, {round(float(t.progress or 0) * 100)}%{who}"
                    + (f", machine {mac}" if mac else "")
                    + (f", order {order_no}" if order_no else "")),
    }


def _blank_machine():
    class _B:
        name = ""
    return _B()


def _resolve_order(db: Session, q: str) -> list:
    q = (q or "").strip()
    if not q:
        return []
    uid = try_uuid(q)
    if uid:
        o = db.query(Order).filter(Order.id == uid).first()
        return [_order_match(o)] if o else []
    exact = db.query(Order).filter(Order.order_number.ilike(q)).all()
    if exact:
        return [_order_match(o) for o in exact[:MAX_MATCHES]]
    starts = db.query(Order).filter(Order.order_number.ilike(f"{q}%")).all()
    have = {str(o.id) for o in exact}
    partial = [o for o in db.query(Order).filter(Order.order_number.ilike(f"%{q}%")).all()
               if str(o.id) not in have]
    return [_order_match(o) for o in (starts + partial)[:MAX_MATCHES]]


def _order_match(o) -> dict:
    return {
        "type": "order",
        "id": str(o.id),
        "label": o.order_number or "Order",
        "detail": o.status,
        "summary": f"Order {o.order_number} — {o.status}, {round(float(o.progress or 0) * 100)}%",
    }


def _resolve_incident(db: Session, q: str) -> list:
    q = (q or "").strip()
    if not q:
        return []
    uid = try_uuid(q)
    if uid:
        i = db.query(Incident).filter(Incident.id == uid).first()
        return [_incident_match(i)] if i else []
    rows = db.query(Incident).all()
    pref = [i for i in rows if str(i.id).lower().startswith(q.lower())]
    if pref:
        return [_incident_match(i) for i in pref[:MAX_MATCHES]]
    part = [i for i in rows if q.lower() in (i.description or "").lower()]
    return [_incident_match(i) for i in part[:MAX_MATCHES]]


def _incident_match(i) -> dict:
    return {
        "type": "incident",
        "id": str(i.id),
        "label": f"{i.severity} incident",
        "detail": i.status,
        "summary": f"{i.severity} {i.status} incident — {(i.description or '')[:100]}",
    }


def _resolve_proposal(db: Session, q: str) -> list:
    q = (q or "").strip()
    if not q:
        return []
    uid = try_uuid(q)
    if uid:
        r = db.query(AIRecommendation).filter(AIRecommendation.id == uid).first()
        return [_proposal_match(r)] if r else []
    rows = db.query(AIRecommendation).filter(
        AIRecommendation.status == "PENDING").order_by(
        AIRecommendation.created_at.desc()).all()
    pref = [r for r in rows if str(r.id).lower().startswith(q.lower())]
    if pref:
        return [_proposal_match(r) for r in pref[:MAX_MATCHES]]
    part = [r for r in rows if q.lower() in (r.recommendation or "").lower()
            or q.lower() in (r.recommendation_type or "").lower()]
    return [_proposal_match(r) for r in part[:MAX_MATCHES]]


def _proposal_match(r) -> dict:
    return {
        "type": "proposal",
        "id": str(r.id),
        "label": (r.recommendation or r.recommendation_type or "Proposal")[:80],
        "detail": r.status,
        "summary": f"{r.recommendation_type} proposal ({r.status}) — {(r.recommendation or '')[:100]}",
    }


def _resolve_employee(db: Session, q: str, codes: dict) -> list:
    q = (q or "").strip()
    if not q:
        return []
    uid = try_uuid(q)
    if uid:
        e = db.query(Employee).filter(Employee.id == uid).first()
        return [_employee_match(db, e, codes)] if e else []
    code = normalize_employee_code(q)
    if code:
        hit = None
        # Stored codes may be hyphenated (EMP-001) or compact (EMP001):
        # try both spellings, hyphenated first (established convention).
        for cand in dict.fromkeys([code, code.replace("-", "")]):
            for c in db.query(WorkerCredential).filter(WorkerCredential.employee_code == cand).all():
                hit = db.query(Employee).filter(Employee.id == c.employee_id).first()
                if hit:
                    break
            if hit:
                break
        return [_employee_match(db, hit, codes)] if hit else []
    ql = q.lower()
    all_emp = db.query(Employee).all()
    exact = [e for e in all_emp if (e.name or "").lower() == ql]
    if exact:
        return [_employee_match(db, e, codes) for e in exact[:MAX_MATCHES]]
    starts = [e for e in all_emp if (e.name or "").lower().startswith(ql)]
    partial = [e for e in all_emp if ql in (e.name or "").lower()
               or ql in (e.role or "").lower()]
    seen = set()
    return _ranked([_employee_match(db, e, codes) for e in exact],
                   [_employee_match(db, e, codes) for e in starts],
                   [_employee_match(db, e, codes) for e in partial], seen)


def _employee_match(db: Session, e, codes: dict) -> dict:
    code = codes.get(e.id)
    avail = (e.availability or "AVAILABLE").upper()
    flagged = "" if avail == "AVAILABLE" and (e.status or "ACTIVE").upper() == "ACTIVE" \
        else f" [{avail}]"
    return {
        "type": "employee",
        "id": str(e.id),
        "label": f"{e.name}" + (f" ({code})" if code else ""),
        "detail": e.role,
        "summary": (f"{e.name}" + (f" ({code})" if code else "")
                     + f" — {e.role}, {avail}{flagged}, "
                     f"{_open_task_count(db, e.id)} open tasks"),
        "unavailable": bool(flagged),
    }


def _resolve_machine(db: Session, q: str) -> list:
    q = (q or "").strip()
    if not q:
        return []
    uid = try_uuid(q)
    if uid:
        m = db.query(Machine).filter(Machine.id == uid).first()
        return [_machine_match(m)] if m else []
    code = normalize_machine_code(q)
    if code:
        hits = [m for m in db.query(Machine).all() if _machine_code(m.name) == code]
        return [_machine_match(m) for m in hits[:MAX_MATCHES]]
    ql = q.lower()
    all_m = db.query(Machine).all()
    exact = [m for m in all_m if (m.name or "").lower() == ql]
    if exact:
        return [_machine_match(m) for m in exact[:MAX_MATCHES]]
    starts = [m for m in all_m if (m.name or "").lower().startswith(ql)]
    partial = [m for m in all_m if ql in (m.name or "").lower()]
    return _ranked([_machine_match(m) for m in exact],
                   [_machine_match(m) for m in starts],
                   [_machine_match(m) for m in partial], set())


def _machine_match(m) -> dict:
    code = _machine_code(m.name)
    return {
        "type": "machine",
        "id": str(m.id),
        "label": code or m.name,
        "detail": m.status,
        "summary": f"{code or m.name} ({m.name}) — {m.status}, health {m.health_status}",
    }


def _resolve_plan(db: Session, q: str) -> list:
    q = (q or "").strip()
    if not q:
        return []
    uid = try_uuid(q)
    if uid:
        p = db.query(WorkPlan).filter(WorkPlan.id == uid).first()
        return [_plan_match(p)] if p else []
    all_p = db.query(WorkPlan).order_by(WorkPlan.created_at.desc()).all()
    ql = q.lower()
    exact = [p for p in all_p if (p.title or "").lower() == ql]
    if exact:
        return [_plan_match(p) for p in exact[:MAX_MATCHES]]
    partial = [p for p in all_p if ql in (p.title or "").lower()]
    return [_plan_match(p) for p in partial[:MAX_MATCHES]]


def _plan_match(p) -> dict:
    return {
        "type": "plan",
        "id": str(p.id),
        "label": p.title or "Untitled plan",
        "detail": p.status,
        "summary": f"Plan '{p.title}' — {p.status}",
    }


def resolve(db: Session, type: str, q: str) -> dict:
    """Shared natural-reference resolution. Returns
    {matches: [{type, id, label, summary, (unavailable?)}], ambiguous: bool}."""
    t = (type or "").strip().lower()
    if t not in TYPES:
        from fastapi import HTTPException
        raise HTTPException(status_code=422,
                            detail=f"Unknown type '{type}'. Use one of {list(TYPES)}.")
    codes = employee_code_map(db) if t in ("task", "employee") else {}
    fn = {
        "task": lambda: _resolve_task(db, q, codes),
        "order": lambda: _resolve_order(db, q),
        "incident": lambda: _resolve_incident(db, q),
        "proposal": lambda: _resolve_proposal(db, q),
        "employee": lambda: _resolve_employee(db, q, codes),
        "machine": lambda: _resolve_machine(db, q),
        "plan": lambda: _resolve_plan(db, q),
    }[t]
    matches = fn()
    _disambiguate(matches)
    return {"matches": matches, "ambiguous": len(matches) > 1}


def _disambiguate(matches: list) -> None:
    """Identical labels (e.g. three tasks all named "Demo CNC milling")
    are useless in a spoken clarification. Suffix duplicates with their
    detail so each option is distinct. Mutates in place."""
    seen = {}
    for m in matches:
        seen[m["label"]] = seen.get(m["label"], 0) + 1
    for m in matches:
        if seen[m["label"]] > 1 and m.get("detail"):
            m["label"] = f"{m['label']} ({m['detail']})"


def resolve_one(db: Session, type: str, q: str):
    """First match or None (for internal callers that handle ambiguity
    themselves). Returns (match_dict_or_None, ambiguous_bool)."""
    res = resolve(db, type, q)
    ms = res["matches"]
    if not ms:
        return None, False
    return ms[0], len(ms) > 1
