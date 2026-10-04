"""Work plans: draft -> approve (creates tasks) -> dispatch (matches + notifies).

Prefixes: /plans, /assignments, /push-tokens (three routers below).
Idempotent dispatch: already-notified assignments are never re-sent.
"""
from datetime import datetime, timezone
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.models.models import (
    AppUser,
    Employee,
    FcmToken,
    Machine,
    Notification,
    PlanAssignment,
    Task,
    WorkPlan,
)
from backend.schemas.plans import (
    AssignmentResponse,
    AssignmentUpdate,
    PairBody,
    PlanCreate,
    PlanResponse,
    SuggestResponse,
    SuggestResult,
    TokenBody,
)
from backend.services.auth import get_current_user, require_manager, require_operator
from backend.services.matcher import match_item

plans = APIRouter()
assignments = APIRouter()
tokens = APIRouter()

PLAN_FLOW = ("DRAFT", "APPROVED", "DISPATCHED", "DONE")
ASSIGN_WORKER_OK = ("ACCEPTED", "IN_PROGRESS", "DONE")


def _plan_or_404(db: Session, plan_id: UUID) -> WorkPlan:
    p = db.query(WorkPlan).filter(WorkPlan.id == plan_id).first()
    if p is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return p


@plans.post("", response_model=PlanResponse)
def create_plan(body: PlanCreate, db: Session = Depends(get_db), user=Depends(require_manager)):
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="Title is required.")
    p = WorkPlan(
        title=body.title.strip(),
        description=(body.description or "").strip() or None,
        payload={"items": [i.model_dump(mode="json") for i in body.items]},
        status="DRAFT",
        created_by=user.id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@plans.get("", response_model=List[PlanResponse])
def list_plans(db: Session = Depends(get_db), user=Depends(require_manager)):
    return db.query(WorkPlan).order_by(WorkPlan.created_at.desc()).all()


@plans.get("/live")
def live_plans(db: Session = Depends(get_db), user=Depends(require_manager)):
    """System-wide live view (no drafting needed): all non-completed tasks
    grouped by order with live fields, plus the unplanned list (tasks in no
    plan). Attach via POST /plans/{id}/items."""
    from backend.services.plan_progress import live_overview
    return live_overview(db)


@plans.get("/{plan_id}", response_model=PlanResponse)
def get_plan(plan_id: UUID, db: Session = Depends(get_db), user=Depends(require_manager)):
    return _plan_or_404(db, plan_id)


@plans.get("/{plan_id}/progress")
def plan_progress_view(plan_id: UUID, db: Session = Depends(get_db),
                       user=Depends(require_manager)):
    """Live progress for one plan: recomputed lifecycle + flags, per-item
    live task state (joined, never snapshotted), and the activity timeline."""
    from backend.services.plan_progress import plan_progress as _progress
    return _progress(db, plan_id)


@plans.post("/{plan_id}/items")
def attach_plan_item(plan_id: UUID, body: dict, db: Session = Depends(get_db),
                     user=Depends(require_manager)):
    """Attach an EXISTING task to an approved plan (e.g. from Unplanned).
    Idempotent: attaching twice returns the existing row. Uses the normal
    plan flow — the plan itself must already be APPROVED or DISPATCHED."""
    from uuid import UUID as _UUID
    p = _plan_or_404(db, plan_id)
    if (p.status or "").upper() not in ("APPROVED", "DISPATCHED"):
        raise HTTPException(status_code=422, detail="Plan must be APPROVED first.")
    try:
        tid = _UUID(str((body or {}).get("task_id") or ""))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail="task_id is required.")
    task = db.query(Task).filter(Task.id == tid).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    existing = db.query(PlanAssignment).filter(
        PlanAssignment.plan_id == plan_id, PlanAssignment.task_id == tid).first()
    if existing is not None:
        return {"assignment_id": str(existing.id), "attached": False}
    row = PlanAssignment(plan_id=plan_id, task_id=tid, status="UNASSIGNED")
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"assignment_id": str(row.id), "attached": True}


@plans.get("/{plan_id}/assignments", response_model=List[AssignmentResponse])
def plan_assignments(plan_id: UUID, db: Session = Depends(get_db), user=Depends(require_manager)):
    _plan_or_404(db, plan_id)
    return db.query(PlanAssignment).filter(PlanAssignment.plan_id == plan_id).all()


@plans.post("/{plan_id}/approve", response_model=PlanResponse)
def approve_plan(plan_id: UUID, db: Session = Depends(get_db), user=Depends(require_manager)):
    """Manager approval: creates one PENDING task per plan item (idempotent —
    approving twice creates nothing new)."""
    p = _plan_or_404(db, plan_id)
    if p.status != "DRAFT":
        return p  # idempotent: approving twice creates nothing new
    items = (p.payload or {}).get("items", []) if isinstance(p.payload, dict) else []
    for idx, item in enumerate(items):
        t = Task(
            name=item.get("task_name") or f"{p.title} — step {idx + 1}",
            description=item.get("description"),
            required_skill=item.get("required_skill"),
            priority=(item.get("priority") or "NORMAL").upper(),
            status="PENDING",
            order_id=item.get("order_id"),
            deadline=item.get("deadline"),
            progress=0.0,
        )
        db.add(t)
        db.flush()
        db.add(PlanAssignment(plan_id=plan_id, task_id=t.id, status="UNASSIGNED"))
    p.status = "APPROVED"
    p.approved_by = user.id
    db.commit()
    db.refresh(p)
    return p


@plans.post("/{plan_id}/dispatch")
def dispatch_plan(plan_id: UUID, db: Session = Depends(get_db), user=Depends(require_manager)):
    """Match + notify. Skips already-notified assignments (idempotent)."""
    from backend.services.push import send_push

    p = _plan_or_404(db, plan_id)
    if p.status not in ("APPROVED", "DISPATCHED"):
        raise HTTPException(status_code=422, detail=f"Plan must be APPROVED first (now {p.status}).")
    items = (p.payload or {}).get("items", []) if isinstance(p.payload, dict) else []
    rows = db.query(PlanAssignment).filter(PlanAssignment.plan_id == plan_id).all()

    dispatched = 0
    skipped = 0
    unassigned = 0
    push_sent = 0
    push_skipped = 0
    now = datetime.now(timezone.utc)
    for idx, row in enumerate(rows):
        if row.notified_at is not None:
            skipped += 1
            continue
        item = items[idx] if idx < len(items) else {}
        res = match_item(db, item)
        emp, mach = res["employee"], res["machine"]
        if emp is None or mach is None and (item.get("machine_type") or "").strip():
            # Incomplete match -> stays UNASSIGNED, managers get a bell.
            row.status = "UNASSIGNED"
            for u in db.query(AppUser).filter(AppUser.active == True, AppUser.role == "MANAGER").all():  # noqa: E712
                db.add(Notification(
                    user_id=u.id,
                    title=f"Plan item needs staffing: {(item.get('task_name') or 'step')[:80]}",
                    body="; ".join(res["reasons"]) or "No match found.",
                    link="tasks", kind="PLAN_NEEDS_STAFF"))
            unassigned += 1
            continue
        task = db.query(Task).filter(Task.id == row.task_id).first() if row.task_id else None
        if task is None:
            unassigned += 1
            continue
        task.employee_id = emp.id
        if mach is not None:
            task.machine_id = mach.id
        row.employee_id = emp.id
        if mach is not None:
            row.machine_id = mach.id
        row.status = "NOTIFIED"
        row.notified_at = now

        # Bell for the linked app user (or managers if worker has no login).
        targets = db.query(AppUser).filter(AppUser.employee_id == emp.id, AppUser.active == True).all()  # noqa: E712
        title = f"New job: {task.name[:80]}"
        mname = (mach.name if mach else "assigned machine")
        body = f"{mname} · skill {task.required_skill or 'general'} · due {task.deadline or 'unspecified'}."
        if targets:
            for u in targets:
                db.add(Notification(user_id=u.id, title=title, body=body, link="tasks", kind="ASSIGNMENT"))
        else:
            for u in db.query(AppUser).filter(AppUser.active == True, AppUser.role == "MANAGER").all():  # noqa: E712
                db.add(Notification(user_id=u.id, title=f"Unlinked worker assigned: {emp.name}",
                                    body=title + " — link a login to " + (emp.name or "") + " for push.",
                                    link="users", kind="PLAN_NEEDS_STAFF"))
        # Push where tokens exist; bell is the guaranteed fallback.
        toks = []
        for u in targets:
            toks += [t.token for t in db.query(FcmToken).filter(FcmToken.user_id == u.id).all()]
        pr = send_push(toks, title, body, {"assignment_id": str(row.id), "task_id": str(task.id)})
        push_sent += pr["sent"]
        push_skipped += pr["skipped"]
        dispatched += 1

    p.status = "DISPATCHED"
    db.commit()
    # F10: every dispatch is organizational memory (counts + who approved).
    try:
        from backend.models.models import FactoryMemory as _FM
        db.add(_FM(
            title=f"Plan dispatched: {p.title[:120]}",
            event_type="PLAN_DISPATCHED",
            description=f"{dispatched} assigned, {skipped} already notified, {unassigned} need staffing. Push sent {push_sent}.",
            metadata_={"plan_id": str(plan_id), "dispatched": dispatched, "skipped": skipped,
                       "unassigned": unassigned, "approved_by": str(user.id)},
        ))
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    return {"plan_id": str(plan_id), "dispatched": dispatched, "skipped": skipped,
            "unassigned": unassigned, "push_sent": push_sent,
            "push_skipped": push_skipped, "push_note": "Bell notification always created; push requires Firebase config."}


SUGGEST_SYSTEM_PROMPT = """You assign factory workers to plan items.
You receive plan items (task, required skill, machine type) plus candidate workers (id, skills, current load, shift) and candidate machines (id, type, health).
Rules:
- Rank exactly one worker per item (highest score first in your reasoning, but output one row per item).
- Prefer: skill match, lowest open_tasks load, HEALTH GOOD machines, matching type.
- Output JSON ONLY: {suggestions: [{assignment_id (exact string from items), employee_id (exact UUID from candidates or null), machine_id (exact UUID or null), score 0-1, reasons[] (short, cite skill/load/health facts), status SUGGESTED or UNASSIGNABLE}]}.
- employee_id null + status UNASSIGNABLE when nobody fits (say why).
- Never invent ids. Unknown items are dropped."""


@plans.post("/{plan_id}/suggest", response_model=SuggestResponse)
def suggest_assignments(plan_id: UUID, db: Session = Depends(get_db), user=Depends(require_operator)):
    """AI-ranked pairings per assignment. Read-only: nothing is assigned.
    Falls back to the deterministic matcher (labeled) when LLM unavailable."""
    from backend.services.llm import LLMUnavailable, complete_json
    from backend.services.suggester import candidate_machines, candidate_workers, validate_suggestions

    p = _plan_or_404(db, plan_id)
    items = (p.payload or {}).get("items", []) if isinstance(p.payload, dict) else []
    rows = db.query(PlanAssignment).filter(PlanAssignment.plan_id == plan_id).all()
    if not rows:
        return {"source": "deterministic", "suggestions": []}

    workers = candidate_workers(db)
    machines = candidate_machines(db)
    valid_a = {str(r.id) for r in rows}
    valid_e = {w["id"] for w in workers}
    valid_m = {m["id"] for m in machines}
    item_list = []
    for idx, row in enumerate(rows):
        item = items[idx] if idx < len(items) else {}
        item_list.append({
            "assignment_id": str(row.id),
            "task_name": item.get("task_name", ""),
            "required_skill": item.get("required_skill", ""),
            "machine_type": item.get("machine_type", ""),
            "current_status": row.status,
        })
    try:
        result = complete_json(
            SUGGEST_SYSTEM_PROMPT,
            {"items": item_list, "workers": workers, "machines": machines},
            SuggestResult,
        )
        suggestions = validate_suggestions(
            [s.model_dump() for s in result.suggestions], valid_a, valid_e, valid_m)
        return {"source": "ai", "suggestions": suggestions}
    except LLMUnavailable:
        pass

    # Deterministic fallback: same matcher as dispatch, labeled honestly.
    fallback = []
    for entry in item_list:
        res = match_item(db, {"required_skill": entry["required_skill"],
                              "machine_type": entry["machine_type"]})
        emp, mac = res["employee"], res["machine"]
        fallback.append({
            "assignment_id": entry["assignment_id"],
            "employee_id": str(emp.id) if emp is not None else None,
            "machine_id": str(mac.id) if mac is not None else None,
            "score": 1.0 if emp is not None else 0.0,
            "reasons": (["Deterministic match (AI unavailable)."] +
                        ([f"Worker load/skill fit: {emp.name}"] if emp is not None else []) +
                        res["reasons"])[:5],
            "status": "SUGGESTED" if emp is not None else "UNASSIGNABLE",
        })
    return {"source": "deterministic", "suggestions": fallback}


@assignments.patch("/{assignment_id}/pair", response_model=AssignmentResponse)
def pair_assignment(assignment_id: UUID, body: PairBody,
                    db: Session = Depends(get_db), user=Depends(require_manager)):
    """Manager applies a chosen pairing (AI-suggested or manual). Validates
    both ids exist; mirrors the pairing onto the linked task."""
    row = db.query(PlanAssignment).filter(PlanAssignment.id == assignment_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if body.employee_id is not None:
        emp = db.query(Employee).filter(Employee.id == body.employee_id).first()
        if emp is None:
            raise HTTPException(status_code=422, detail="Unknown employee_id.")
        row.employee_id = emp.id
    if body.machine_id is not None:
        mac = db.query(Machine).filter(Machine.id == body.machine_id).first()
        if mac is None:
            raise HTTPException(status_code=422, detail="Unknown machine_id.")
        row.machine_id = mac.id
    if row.task_id:
        task = db.query(Task).filter(Task.id == row.task_id).first()
        if task is not None:
            if row.employee_id:
                task.employee_id = row.employee_id
            if row.machine_id:
                task.machine_id = row.machine_id
    db.commit()
    db.refresh(row)
    return row


@assignments.get("/mine", response_model=List[AssignmentResponse])
def my_assignments(db: Session = Depends(get_db), user=Depends(get_current_user)):
    from backend.core.config import settings
    # DEV ONLY view-as switch: the bypass login has no employee link, so by
    # default it sees all active assignments; DEV_VIEW_AS=<name> scopes to
    # one worker to prove per-worker scoping. Real logins use their link.
    if settings.AUTH_DISABLED:
        view_as = (settings.DEV_VIEW_AS or "").strip().lower()
        q = db.query(PlanAssignment).filter(
            PlanAssignment.status.in_(["NOTIFIED", "ACCEPTED", "IN_PROGRESS"]))
        if view_as:
            emp = db.query(Employee).filter(Employee.name.ilike(f"%{view_as}%")).first()
            if emp is None:
                return []
            q = q.filter(PlanAssignment.employee_id == emp.id)
        return q.order_by(PlanAssignment.created_at.desc()).all()
    if not user.employee_id:
        return []
    return (
        db.query(PlanAssignment)
        .filter(PlanAssignment.employee_id == user.employee_id)
        .order_by(PlanAssignment.created_at.desc())
        .all()
    )


@assignments.patch("/{assignment_id}", response_model=AssignmentResponse)
def update_assignment(assignment_id: UUID, body: AssignmentUpdate,
                      db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Worker (own assignment) or manager/operator: advance status."""
    st = (body.status or "").upper()
    if st not in ASSIGN_WORKER_OK:
        raise HTTPException(status_code=422, detail=f"Use one of {list(ASSIGN_WORKER_OK)}.")
    row = db.query(PlanAssignment).filter(PlanAssignment.id == assignment_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if user.role == "WORKER" and (not user.employee_id or row.employee_id != user.employee_id):
        raise HTTPException(status_code=403, detail="Not your assignment.")
    row.status = st
    row.responded_at = datetime.now(timezone.utc)
    if row.task_id:
        task = db.query(Task).filter(Task.id == row.task_id).first()
        if task is not None:
            task.status = "IN_PROGRESS" if st in ("ACCEPTED", "IN_PROGRESS") else "DONE"
            if st == "DONE":
                task.progress = 1.0
    db.commit()
    db.refresh(row)
    return row


@tokens.post("", response_model=dict)
def register_token(body: TokenBody, db: Session = Depends(get_db), user=Depends(get_current_user)):
    tok = (body.token or "").strip()
    if not tok:
        raise HTTPException(status_code=422, detail="Token is required.")
    existing = db.query(FcmToken).filter(FcmToken.token == tok).first()
    if existing is None:
        db.add(FcmToken(user_id=user.id, token=tok, platform=(body.platform or "android")[:20]))
        db.commit()
    return {"ok": True}
