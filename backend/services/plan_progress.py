"""Live work-plan progress (Part 1: plan tracking). Read-only joins.

Source of truth: the stored plan keeps title, approval state, item order
(payload snapshot) and who approved. Everything live — task status,
progress, quantities, assignee, machine, deadline — is joined from the real
rows on every read, never snapshotted. No schema changes.

Lifecycle (recomputed on read, deterministic):
  DRAFT -> APPROVED/DISPATCHED (stored milestone) -> IN_PROGRESS (any item
  started) -> COMPLETED (every item closed).
Flags (overlays, also recomputed): BLOCKED (machine has an OPEN incident,
or worker unavailable/on-leave/inactive), OVERDUE (past deadline, not done).

"Done/closed" = DONE, COMPLETED or CANCELLED (cancelled never blocks
COMPLETED). Progress = average of item progress (done counts as 1.0).
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.models.models import (
    AppUser,
    Employee,
    FactoryMemory,
    Incident,
    Machine,
    Order,
    PlanAssignment,
    ProductionRun,
    Task,
    WorkerCredential,
    WorkPlan,
)

DONE_TASK = {"DONE", "COMPLETED", "CANCELLED"}
ACTIVE_TASK = {"IN_PROGRESS"}
UNAVAILABLE = {"BUSY", "UNAVAILABLE", "ON_LEAVE"}
TIMELINE_TYPES = ("WORKER_UPDATE", "ADMIN_DECISION", "PLAN_DISPATCHED")


def employee_code_for(db: Session, employee_id):
    """Employee code only. Never email, username, password or hash."""
    if employee_id is None:
        return None
    cred = db.query(WorkerCredential).filter(
        WorkerCredential.employee_id == employee_id).first()
    return cred.employee_code if cred and cred.employee_code else None


class _Ctx:
    """Bulk-preloaded lookups so live views stay fast (one query per
    table instead of N+1 over the network)."""

    def __init__(self, db: Session, tasks):
        self.employees = {e.id: e for e in db.query(Employee).all()}
        self.codes = {c.employee_id: c.employee_code
                      for c in db.query(WorkerCredential).all() if c.employee_code}
        self.machines = {m.id: m for m in db.query(Machine).all()}
        self.open_inc = {}
        for i in db.query(Incident).filter(Incident.status == "OPEN").all():
            if i.machine_id and i.machine_id not in self.open_inc:
                self.open_inc[i.machine_id] = i
        oids = {t.order_id for t in tasks if t.order_id}
        self.orders = {o.id: o for o in db.query(Order).filter(
            Order.id.in_(list(oids))).all()} if oids else {}
        self.runs = {}
        if oids:
            for r in db.query(ProductionRun).filter(
                    ProductionRun.order_id.in_(list(oids))).all():
                self.runs.setdefault(r.order_id, []).append(r)

    def run_for(self, task: Task):
        runs = self.runs.get(task.order_id) or []
        if not runs:
            return None
        return next((r for r in runs if r.task_id == task.id), runs[0])


def _run_for(db: Session, task: Task):
    if task.order_id is None:
        return None
    runs = db.query(ProductionRun).filter(ProductionRun.order_id == task.order_id).all()
    if not runs:
        return None
    return next((r for r in runs if r.task_id == task.id), runs[0])


def task_live(db: Session, task: Task, ctx=None) -> dict:
    """One task with live assignee/machine/order/run state + blockers."""
    ctx = ctx or _Ctx(db, [task])
    emp = None
    if task.employee_id:
        e = ctx.employees.get(task.employee_id)
        if e is not None:
            emp = {
                "id": str(e.id),
                "name": e.name,
                "employee_code": ctx.codes.get(e.id),
                "availability": e.availability,
                "status": e.status,
            }
    mac = None
    open_incident = None
    if task.machine_id:
        m = ctx.machines.get(task.machine_id)
        if m is not None:
            mac = {"id": str(m.id), "name": m.name}
            inc = ctx.open_inc.get(m.id)
            if inc is not None:
                open_incident = {"id": str(inc.id), "severity": inc.severity}
    order = None
    if task.order_id:
        o = ctx.orders.get(task.order_id)
        if o is not None:
            order = {"id": str(o.id), "order_number": o.order_number}
    run = ctx.run_for(task)
    qty_done = run.quantity_completed if run else None
    qty_target = run.quantity_target if run else None

    status = (task.status or "PENDING").upper()
    done = status in DONE_TASK
    progress = task.progress if task.progress is not None else (1.0 if done else 0.0)
    try:
        progress = max(0.0, min(1.0, float(progress)))
    except (TypeError, ValueError):
        progress = 1.0 if done else 0.0
    if done:
        progress = 1.0
    started = status in ACTIVE_TASK or progress > 0 or task.start_time is not None \
        or (qty_done or 0) > 0

    blocked_reason = None
    if open_incident is not None:
        blocked_reason = (f"Machine has OPEN incident "
                          f"({open_incident['severity']})")
    elif emp is not None and ((emp.get("availability") or "AVAILABLE").upper() in UNAVAILABLE
                              or (emp.get("status") or "ACTIVE").upper() != "ACTIVE"):
        blocked_reason = (f"Worker {emp['name']} is "
                          f"{(emp.get('availability') or emp.get('status') or 'unavailable')}")

    overdue = False
    if not done and task.deadline is not None:
        try:
            dl = task.deadline
            if dl.tzinfo is None:
                dl = dl.replace(tzinfo=timezone.utc)
            overdue = dl < datetime.now(timezone.utc)
        except Exception:
            overdue = False

    return {
        "id": str(task.id),
        "name": task.name,
        "status": status,
        "progress": progress,
        "started": started,
        "done": done,
        "priority": task.priority,
        "required_skill": task.required_skill,
        "deadline": task.deadline.isoformat() if task.deadline else None,
        "start_time": task.start_time.isoformat() if task.start_time else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        "quantity_completed": qty_done,
        "quantity_target": qty_target,
        "employee": emp,
        "machine": mac,
        "order": order,
        "open_incident": open_incident,
        "blocked_reason": blocked_reason,
        "blocked": blocked_reason is not None,
        "overdue": overdue,
    }


def compute_plan_state(items_live: list, stored_status: str) -> dict:
    """Deterministic lifecycle + flags from live items."""
    if stored_status == "DRAFT" or not items_live:
        return {"lifecycle": stored_status, "flags": []}
    if all(i.get("done") or i.get("deleted") for i in items_live):
        lifecycle = "COMPLETED"
    elif any(i.get("started") for i in items_live if not i.get("deleted")):
        lifecycle = "IN_PROGRESS"
    else:
        lifecycle = stored_status if stored_status in ("APPROVED", "DISPATCHED") else "APPROVED"
    flags = []
    if any(i.get("blocked") for i in items_live):
        flags.append("BLOCKED")
    if any(i.get("overdue") for i in items_live):
        flags.append("OVERDUE")
    return {"lifecycle": lifecycle, "flags": flags}


def _approved_by(db: Session, plan: WorkPlan):
    if not plan.approved_by:
        return None
    u = db.query(AppUser).filter(AppUser.id == plan.approved_by).first()
    if u is None:
        return {"id": str(plan.approved_by), "name": None}
    return {"id": str(u.id), "name": u.name}


def _timeline(db: Session, plan_id, task_ids: set) -> tuple:
    """Memory entries for this plan + per-task started/finished estimates.

    Started/finished come from WORKER_UPDATE entries; anything known only
    via task.updated_at is labeled estimated (last-updated, not an event).
    """
    task_strs = {str(t) for t in task_ids}
    rows = db.query(FactoryMemory).filter(
        FactoryMemory.event_type.in_(list(TIMELINE_TYPES))).order_by(
        FactoryMemory.created_at.asc()).all()
    entries = []
    starts = {}
    finishes = {}
    for m in rows:
        meta = m.metadata_ or {}
        mid_plan = str(meta.get("plan_id") or "") == str(plan_id)
        mid_task = (str(m.task_id) if m.task_id else None) in task_strs \
            or str(meta.get("task_id") or "") in task_strs
        if not (mid_plan or mid_task):
            continue
        entries.append({
            "id": str(m.id),
            "at": m.created_at.isoformat() if m.created_at else None,
            "kind": m.event_type,
            "title": m.title,
            "description": m.description,
            "task_id": str(m.task_id) if m.task_id else str(meta.get("task_id") or "") or None,
        })
        if m.event_type == "WORKER_UPDATE":
            tid = str(m.task_id) if m.task_id else str(meta.get("task_id") or "")
            to_s = str(meta.get("to_status") or "").upper()
            if to_s == "IN_PROGRESS" and tid and tid not in starts:
                starts[tid] = m.created_at.isoformat() if m.created_at else None
            if to_s in ("DONE", "COMPLETED") and tid and tid not in finishes:
                finishes[tid] = m.created_at.isoformat() if m.created_at else None
    entries.sort(key=lambda e: e["at"] or "")
    return entries, starts, finishes


def plan_progress(db: Session, plan_id) -> dict:
    """Full live progress payload for one plan. No snapshots of live state."""
    from fastapi import HTTPException
    from uuid import UUID as _UUID
    try:
        pid = plan_id if isinstance(plan_id, _UUID) else _UUID(str(plan_id))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="Plan not found")
    plan = db.query(WorkPlan).filter(WorkPlan.id == pid).first()
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    rows = db.query(PlanAssignment).filter(PlanAssignment.plan_id == plan.id).all()
    task_ids = {r.task_id for r in rows if r.task_id}
    plan_tasks = [db.query(Task).filter(Task.id == r.task_id).first()
                  if r.task_id else None for r in rows]
    ctx = _Ctx(db, [t for t in plan_tasks if t is not None])

    items = []
    for row, task in zip(rows, plan_tasks):
        if task is None:
            items.append({
                "assignment_id": str(row.id),
                "assignment_status": row.status,
                "deleted": True,
                "done": True,
                "started": False,
                "blocked": False,
                "overdue": False,
                "task": None,
            })
            continue
        live = task_live(db, task, ctx)
        items.append({
            "assignment_id": str(row.id),
            "assignment_status": row.status,
            "deleted": False,
            "done": live["done"],
            "started": live["started"],
            "blocked": live["blocked"],
            "overdue": live["overdue"],
            "task": live,
        })

    state = compute_plan_state(items, (plan.status or "DRAFT").upper())
    n = len(items)
    progress = round(sum((i["task"] or {}).get("progress", 0.0)
                         if not i.get("deleted") else 1.0 for i in items) / n, 3) if n else 0.0
    counts = {
        "total": n,
        "done": sum(1 for i in items if i.get("done")),
        "active": sum(1 for i in items if not i.get("done") and not i.get("deleted")
                      and ((i["task"] or {}).get("status") in ACTIVE_TASK)),
        "pending": sum(1 for i in items if not i.get("done") and not i.get("deleted")
                       and ((i["task"] or {}).get("status") == "PENDING")),
        "blocked": sum(1 for i in items if i.get("blocked")),
        "overdue": sum(1 for i in items if i.get("overdue")),
    }
    timeline, starts, finishes = _timeline(db, plan.id, task_ids)
    for it in items:
        tid = (it.get("task") or {}).get("id")
        it["started_at"] = starts.get(tid)
        it["finished_at"] = finishes.get(tid)
        it["started_estimated"] = starts.get(tid) is None and bool(it.get("started"))
        it["finished_estimated"] = finishes.get(tid) is None and bool(it.get("done"))

    return {
        "plan": {
            "id": str(plan.id),
            "title": plan.title,
            "description": plan.description,
            "stored_status": (plan.status or "DRAFT").upper(),
            "status": state["lifecycle"],
            "flags": state["flags"],
            "progress": progress,
            "counts": counts,
            "approved_by": _approved_by(db, plan),
            "approved_at": plan.updated_at.isoformat()
            if plan.updated_at and (plan.status or "").upper() != "DRAFT" else None,
            "created_at": plan.created_at.isoformat() if plan.created_at else None,
        },
        "items": items,
        "timeline": timeline,
    }


def live_overview(db: Session) -> dict:
    """System-wide live view: all non-completed tasks grouped by order,
    plus tasks attached to no plan (unplanned)."""
    tasks = db.query(Task).filter(~Task.status.in_(list(DONE_TASK))).all()
    planned_ids = {r.task_id for r in db.query(PlanAssignment.task_id).all() if r.task_id}
    ctx = _Ctx(db, tasks)
    groups = {}
    for t in tasks:
        live = task_live(db, t, ctx)
        key = str(t.order_id) if t.order_id else "__none__"
        g = groups.get(key)
        if g is None:
            order_number = live["order"]["order_number"] if live["order"] else None
            g = groups[key] = {
                "order": {"id": str(t.order_id), "order_number": order_number}
                if t.order_id else None,
                "tasks": [],
            }
        live["in_plan"] = t.id in planned_ids
        g["tasks"].append(live)
    ordered = sorted(groups.values(),
                     key=lambda g: (g["order"] is None, (g["order"] or {}).get("order_number") or ""))
    unplanned = [t for g in ordered for t in g["tasks"] if not t["in_plan"]]
    return {"groups": ordered, "unplanned": unplanned,
            "counts": {"open": len(tasks), "unplanned": len(unplanned)}}
