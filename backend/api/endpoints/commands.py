"""Direct FAST commands (voice/text admin actions).

Prefix /ai/commands. ONE call resolves, defaults, validates, writes and
audits — no LLM inside (target <500 ms). ASK autonomy routes the same
resolved params into the existing proposal flow instead of executing.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.services import commands as svc

router = APIRouter()


class TaskCommand(BaseModel):
    text: str = ""
    employee_ref: Optional[str] = None
    employee_id: Optional[str] = None
    machine_ref: Optional[str] = None
    machine_id: Optional[str] = None
    order_ref: Optional[str] = None
    order_id: Optional[str] = None
    priority: Optional[str] = None
    deadline_text: Optional[str] = None
    deadline: Optional[str] = None
    description: Optional[str] = None
    autopilot: bool = False
    source: str = "voice"


class OrderCommand(BaseModel):
    product: str = ""
    quantity: int = 0
    customer: Optional[str] = None
    autopilot: bool = False
    source: str = "voice"


class AssignCommand(BaseModel):
    text: str = ""
    task_ref: Optional[str] = None
    task_id: Optional[str] = None
    task_ids: Optional[list] = None
    employee_ref: Optional[str] = None
    employee_id: Optional[str] = None
    machine_ref: Optional[str] = None
    machine_id: Optional[str] = None
    autopilot: bool = False
    confirmed: bool = False
    source: str = "voice"


class ChangeCommand(BaseModel):
    text: str = ""
    task_ref: Optional[str] = None
    task_id: Optional[str] = None
    employee_ref: Optional[str] = None
    employee_id: Optional[str] = None
    machine_ref: Optional[str] = None
    machine_id: Optional[str] = None
    deadline_text: Optional[str] = None
    deadline: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    autopilot: bool = False
    confirmed: bool = False
    source: str = "voice"


class MaintenanceCommand(BaseModel):
    machine_ref: Optional[str] = None
    machine_id: Optional[str] = None
    issue: Optional[str] = None
    autopilot: bool = False
    source: str = "voice"


def _maybe_propose(db: Session, result: dict, body, kind: str):
    """ASK mode is handled by callers via svc.propose_instead; this helper
    only normalizes the envelope."""
    return result


def _dispatch_ask(db: Session, *, action_type: str, params: dict, reason: str):
    return svc.propose_instead(db, action_type=action_type, params=params, reason=reason)


def _autonomy(db: Session):
    return svc.get_autonomy(db)


def _guard_forbidden(*parts):
    """Tier 3: no delete/credentials/availability/profile action may ever run
    through a command endpoint, regardless of which tool/route reached it."""
    from backend.services import command_policy as pol
    text = " ".join(str(p or "") for p in parts)
    forbidden, reason = pol.is_forbidden(text)
    if forbidden:
        raise HTTPException(status_code=422, detail=pol.refusal_for(reason))


@router.post("/task")
def command_task(body: TaskCommand, db: Session = Depends(get_db)):
    from backend.services import command_policy as pol
    forbidden, reason = pol.is_forbidden(
        f"{body.text} {body.employee_ref or ''} {body.machine_ref or ''}")
    if forbidden:
        raise HTTPException(status_code=422, detail=pol.refusal_for(reason))
    if not (body.text or "").strip():
        raise HTTPException(status_code=422, detail="Describe the task to create.")
    if _autonomy(db) == "ASK" and not body.autopilot:
        from backend.services.resolve import resolve_one
        from uuid import UUID as _UUID
        params = {"task_name": pol.task_name_from(body.text)}
        if body.employee_id or body.employee_ref:
            m, amb = ({"id": body.employee_id}, False) if body.employee_id else \
                resolve_one(db, "employee", body.employee_ref or "")
            if amb:
                from backend.services.resolve import resolve as _res
                opts = [x["label"] for x in _res(db, "employee", body.employee_ref or "")["matches"][:3]]
                raise HTTPException(status_code=409, detail={"question": "Which worker?", "options": opts})
            if m:
                params["employee_id"] = m["id"]
        if body.machine_id or body.machine_ref:
            m, amb = ({"id": body.machine_id}, False) if body.machine_id else \
                resolve_one(db, "machine", body.machine_ref or "")
            if amb:
                raise HTTPException(status_code=409, detail={"question": "Which machine?",
                                                             "options": []})
            if m:
                params["machine_id"] = m["id"]
        if body.order_id or body.order_ref:
            m, amb = ({"id": body.order_id}, False) if body.order_id else \
                resolve_one(db, "order", body.order_ref or "")
            if m and not amb:
                params["order_id"] = m["id"]
        return _dispatch_ask(db, action_type="DRAFT_ASSIGNMENT", params=params,
                             reason=f"Voice request: {body.text}"[:500])
    return svc.run_create_task(
        db, text=body.text, employee_ref=body.employee_ref, employee_id=body.employee_id,
        machine_ref=body.machine_ref, machine_id=body.machine_id,
        order_ref=body.order_ref, order_id=body.order_id,
        priority=body.priority, deadline_text=body.deadline_text,
        explicit_deadline=body.deadline, description=body.description,
        autopilot=body.autopilot, source=body.source)


@router.post("/order")
def command_order(body: OrderCommand, db: Session = Depends(get_db)):
    _guard_forbidden(body.product, body.customer)
    if not (body.product or "").strip():
        raise HTTPException(status_code=422, detail="Say what the order is for.")
    if _autonomy(db) == "ASK" and not body.autopilot:
        return _dispatch_ask(db, action_type="CREATE_ORDER",
                             params={"product": body.product, "quantity": body.quantity,
                                     "customer": body.customer},
                             reason=f"Voice request: order {body.quantity} x {body.product}")
    return svc.run_create_order(db, product=body.product, quantity=body.quantity,
                                customer=body.customer, autopilot=body.autopilot,
                                source=body.source)


@router.post("/assign")
def command_assign(body: AssignCommand, db: Session = Depends(get_db)):
    _guard_forbidden(body.text, body.task_ref, body.employee_ref, body.machine_ref)
    if _autonomy(db) == "ASK" and not body.autopilot:
        from backend.services.resolve import resolve_one
        params = {}
        if body.task_id:
            params["task_id"] = body.task_id
        elif body.task_ref:
            m, amb = resolve_one(db, "task", body.task_ref)
            if amb:
                raise HTTPException(status_code=409, detail={"question": "Which task?",
                                                             "options": []})
            if m:
                params["task_id"] = m["id"]
        if body.employee_id:
            params["employee_id"] = body.employee_id
        elif body.employee_ref:
            m, amb = resolve_one(db, "employee", body.employee_ref)
            if m and not amb:
                params["employee_id"] = m["id"]
        if body.machine_id:
            params["machine_id"] = body.machine_id
        elif body.machine_ref:
            m, amb = resolve_one(db, "machine", body.machine_ref)
            if m and not amb:
                params["machine_id"] = m["id"]
        if "task_id" not in params or ("employee_id" not in params and "machine_id" not in params):
            raise HTTPException(status_code=422, detail="Say which task and who should do it.")
        return _dispatch_ask(db, action_type="REASSIGN_TASK", params=params,
                             reason="Voice request: assign task")
    return svc.run_assign(
        db, task_ref=body.task_ref, task_id=body.task_id, task_ids=body.task_ids,
        employee_ref=body.employee_ref, employee_id=body.employee_id,
        machine_ref=body.machine_ref, machine_id=body.machine_id,
        autopilot=body.autopilot, source=body.source, confirmed=body.confirmed)


@router.post("/change")
def command_change(body: ChangeCommand, db: Session = Depends(get_db)):
    _guard_forbidden(body.text, body.task_ref, body.status,
                     body.employee_ref, body.machine_ref)
    if _autonomy(db) == "ASK" and not body.autopilot:
        raise HTTPException(status_code=422, detail="ASK mode: describe the change on screen instead.")
    return svc.run_change(
        db, task_ref=body.task_ref, task_id=body.task_id,
        employee_ref=body.employee_ref, employee_id=body.employee_id,
        machine_ref=body.machine_ref, machine_id=body.machine_id,
        deadline_text=body.deadline_text, explicit_deadline=body.deadline,
        priority=body.priority, status=body.status,
        autopilot=body.autopilot, source=body.source, confirmed=body.confirmed)


@router.post("/maintenance")
def command_maintenance(body: MaintenanceCommand, db: Session = Depends(get_db)):
    _guard_forbidden(body.issue, body.machine_ref)
    if _autonomy(db) == "ASK" and not body.autopilot:
        from backend.services.resolve import resolve_one
        params = {"issue": (body.issue or "Voice-requested check")[:200]}
        if body.machine_id:
            params["machine_id"] = body.machine_id
        elif body.machine_ref:
            m, amb = resolve_one(db, "machine", body.machine_ref)
            if m and not amb:
                params["machine_id"] = m["id"]
        if "machine_id" not in params:
            raise HTTPException(status_code=422, detail="Say which machine needs maintenance.")
        return _dispatch_ask(db, action_type="SCHEDULE_MAINTENANCE", params=params,
                             reason=f"Voice request: maintenance for {body.machine_ref or ''}")
    return svc.run_maintenance(
        db, machine_ref=body.machine_ref, machine_id=body.machine_id,
        issue=body.issue, autopilot=body.autopilot, source=body.source)


@router.post("/{command_id}/undo")
def undo(command_id: str, db: Session = Depends(get_db)):
    return svc.undo_command(db, command_id)


@router.post("/undo-last")
def undo_last(db: Session = Depends(get_db)):
    mem = svc.latest_undoable(db)
    if mem is None:
        raise HTTPException(status_code=404, detail="Nothing recent to undo.")
    return svc.undo_command(db, str(mem.id))


@router.get("/recent")
def recent(limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    return svc.recent_commands(db, limit)


@router.get("/autonomy")
def get_autonomy(db: Session = Depends(get_db)):
    return {"autonomy": svc.get_autonomy(db)}


class AutonomyBody(BaseModel):
    autonomy: str


@router.put("/autonomy")
def put_autonomy(body: AutonomyBody, db: Session = Depends(get_db)):
    return {"autonomy": svc.set_autonomy(db, body.autonomy)}
