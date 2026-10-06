"""Operations reports (Phase 5). Prefix /reports.

Deterministic aggregates only — no LLM. build_weekly()/build_period()/
build_order_report() are pure functions of the DB session (+ bounds) so they
can be unit-tested without HTTP. Nothing here ever writes to the database:
reports are calculated on demand, so a completed order's final report is
automatically available the moment its status changes — no generation step,
no duplicates.

Weeks are Monday 00:00 -> Sunday 23:59:59 UTC; ?week_offset=0 is this week.
Months are calendar months UTC; ?month=YYYY-MM.

Completion honesty: no completed_at timestamp exists on any operational
table, so "completed in period" is proxied by last update (updated_at).
Responses label this basis explicitly instead of claiming true completion
timestamps.
"""
import calendar
import re
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID

from backend.db.database import get_db
from backend.db.scoping import SCOPE_KEY
from backend.models.models import (
    AIRecommendation,
    Employee,
    FactoryMemory,
    Incident,
    Machine,
    MachineTelemetry,
    Maintenance,
    Order,
    ProductionRun,
    Task,
)

router = APIRouter()

CLOSED_ORDER = ("COMPLETED", "DONE", "CANCELLED")
FINAL_ORDER = ("COMPLETED", "DONE")
CLOSED_TASK = ("COMPLETED", "DONE", "CANCELLED")
ACTIVE_INCIDENT = ("OPEN", "IN_PROGRESS")
ACTIVE_RUN = ("IN_PROGRESS", "RUNNING")

COMPLETED_BASIS_NOTE = (
    "completed counts use last update (updated_at) as a proxy; "
    "no completion timestamp exists on operational tables"
)


def _require_scope(db: Session):
    scope = db.info.get(SCOPE_KEY)
    if not scope:
        raise HTTPException(status_code=400, detail="No active factory. Send the X-Factory-Id header.")
    return scope


def _as_utc(dt):
    if dt is None:
        return None
    try:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _in_range(dt, start, end) -> bool:
    d = _as_utc(dt)
    return d is not None and start <= d <= end


def _iso(dt):
    d = _as_utc(dt)
    try:
        return d.isoformat() if d else None
    except Exception:
        return None


def week_bounds(offset: int = 0):
    now = datetime.now(timezone.utc)
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    start = monday - timedelta(weeks=offset)
    return start, start + timedelta(days=7) - timedelta(seconds=1)


_MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def month_bounds(month: str):
    m = _MONTH_RE.match((month or "").strip())
    if not m:
        raise HTTPException(status_code=422, detail=f"Invalid month '{month}'. Use YYYY-MM.")
    year, mon = int(m.group(1)), int(m.group(2))
    start = datetime(year, mon, 1, tzinfo=timezone.utc)
    last_day = calendar.monthrange(year, mon)[1]
    end = datetime(year, mon, last_day, 23, 59, 59, tzinfo=timezone.utc)
    return start, end


def _code(name: str) -> str:
    m = re.match(r"^(M-\d{3})", (name or "").strip())
    return m.group(1) if m else (name or "")[:12]


def build_period(db: Session, start: datetime, end: datetime) -> dict:
    """Shared period aggregation. Reads only — never writes."""
    now = datetime.now(timezone.utc)

    orders = db.query(Order).all()
    completed = [o for o in orders if (o.status or "").upper() in CLOSED_ORDER]
    completed_in_period = [o for o in completed if _in_range(o.updated_at, start, end)]
    late = []
    for o in orders:
        if (o.status or "").upper() in CLOSED_ORDER or not o.deadline:
            continue
        dl = _as_utc(o.deadline)
        if dl is not None and dl < now:
            late.append(o)

    runs = db.query(ProductionRun).all()
    runs_completed = [r for r in runs if (r.status or "").upper() in CLOSED_ORDER]
    target_qty = sum(int(r.quantity_target or 0) for r in runs)
    done_qty = sum(int(r.quantity_completed or 0) for r in runs)

    tasks = db.query(Task).all()
    tasks_completed = [t for t in tasks if (t.status or "").upper() in CLOSED_TASK]
    tasks_open = [t for t in tasks if (t.status or "").upper() not in CLOSED_TASK]
    tasks_active = [t for t in tasks if (t.status or "").upper() == "IN_PROGRESS"]

    incidents = db.query(Incident).all()
    raised = [i for i in incidents if _in_range(i.created_at, start, end)]
    currently_open = [i for i in incidents if (i.status or "").upper() in ACTIVE_INCIDENT]
    severity_counts: dict = {}
    for i in raised:
        sev = (i.severity or "UNKNOWN").upper()
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    machines = {m.id: m for m in db.query(Machine).all()}
    per_machine: dict = {}
    for i in raised:
        if i.machine_id is None:
            continue
        per_machine[i.machine_id] = per_machine.get(i.machine_id, 0) + 1
    top_failing = sorted(
        (
            {
                "machine_id": str(mid),
                "code": _code((machines[mid].name if mid in machines else "")),
                "name": (machines[mid].name if mid in machines else "Unknown"),
                "incidents": n,
            }
            for mid, n in per_machine.items()
        ),
        key=lambda d: -d["incidents"],
    )[:5]
    runs_per_machine: dict = {}
    for r in runs:
        if r.machine_id is None:
            continue
        runs_per_machine[r.machine_id] = runs_per_machine.get(r.machine_id, 0) + 1
    machine_activity = sorted(
        (
            {
                "machine_id": str(mid),
                "code": _code((machines[mid].name if mid in machines else "")),
                "name": (machines[mid].name if mid in machines else "Unknown"),
                "runs": n,
            }
            for mid, n in runs_per_machine.items()
        ),
        key=lambda d: -d["runs"],
    )[:5]

    maint = db.query(Maintenance).filter(
        Maintenance.created_at >= start, Maintenance.created_at <= end
    ).all()
    maint_by_status: dict = {}
    for mrow in maint:
        st = (mrow.status or "UNKNOWN").upper()
        maint_by_status[st] = maint_by_status.get(st, 0) + 1

    samples = db.query(MachineTelemetry).filter(
        MachineTelemetry.timestamp >= start, MachineTelemetry.timestamp <= end
    ).all()
    abnormal_count = 0
    try:
        from backend.services.abnormality import default_thresholds, evaluate_telemetry
        base = default_thresholds()
        for s in samples:
            try:
                if evaluate_telemetry(s, base)["abnormal"]:
                    abnormal_count += 1
            except Exception:
                continue
    except Exception:
        abnormal_count = 0

    emp_names = {e.id: e.name for e in db.query(Employee).all()}
    workload: dict = {}
    for t in tasks_open:
        if t.employee_id is None:
            continue
        workload[t.employee_id] = workload.get(t.employee_id, 0) + 1
    top_workload = sorted(
        (
            {"employee_id": str(eid), "name": emp_names.get(eid) or "Unknown", "open_tasks": n}
            for eid, n in workload.items()
        ),
        key=lambda d: -d["open_tasks"],
    )[:5]

    mems = db.query(FactoryMemory).filter(
        FactoryMemory.created_at >= start, FactoryMemory.created_at <= end
    ).all()
    decisions = [m for m in mems if m.event_type == "ADMIN_DECISION"]
    recs = db.query(AIRecommendation).filter(
        AIRecommendation.created_at >= start, AIRecommendation.created_at <= end
    ).all()
    approved = sum(1 for r in recs if r.status == "APPROVED")
    rejected = sum(1 for r in recs if r.status == "REJECTED")

    return {
        "orders": {
            "completed_this_week": len(completed_in_period),
            "completed_total": len(completed),
            "completed_basis": COMPLETED_BASIS_NOTE,
            "late_now": len(late),
            "late_orders": [
                {"order_number": o.order_number, "deadline": _iso(o.deadline),
                 "status": o.status} for o in late[:20]
            ],
            "active_total": sum(1 for o in orders if (o.status or "").upper() not in CLOSED_ORDER),
        },
        "production": {
            "run_count": len(runs),
            "completed_runs": len(runs_completed),
            "target_quantity": target_qty,
            "completed_quantity": done_qty,
        },
        "tasks": {
            "total": len(tasks),
            "completed": len(tasks_completed),
            "open": len(tasks_open),
            "in_progress": len(tasks_active),
        },
        "downtime": {
            "incidents_raised_this_week": len(raised),
            "currently_open": len(currently_open),
            "severity_counts": severity_counts,
        },
        "top_failing_machines": top_failing,
        "machines": {
            "total": len(machines),
            "activity": machine_activity,
        },
        "maintenance": {
            "events_this_period": len(maint),
            "by_status": maint_by_status,
        },
        "telemetry": {
            "samples_this_period": len(samples),
            "abnormal_readings": abnormal_count,
            "abnormal_basis": "default detection thresholds; per-machine profile thresholds may differ",
        },
        "employees": {
            "assigned_open_tasks": sum(workload.values()),
            "top_workload": top_workload,
        },
        "decisions": {
            "admin_decisions_this_week": len(decisions),
            "recommendations_approved": approved,
            "recommendations_rejected": rejected,
        },
    }


def build_weekly(db: Session, start: datetime, end: datetime) -> dict:
    """Weekly aggregation. Reads only — never writes. Kept for compatibility."""
    return build_period(db, start, end)


def _task_employee_names(db: Session, tasks) -> dict:
    ids = {t.employee_id for t in tasks if t.employee_id is not None}
    if not ids:
        return {}
    return {e.id: e.name for e in db.query(Employee).filter(Employee.id.in_(list(ids))).all()}


def build_order_report(db: Session, order_id: UUID) -> dict:
    """Final/current report for one order. Reads only — never writes.

    The order is resolved through the scoped session, so a cross-factory or
    nonexistent id is a plain 404 with no information leak.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    is_final = (order.status or "").strip().upper() in FINAL_ORDER

    runs = db.query(ProductionRun).filter(ProductionRun.order_id == order.id).all()
    run_target = sum(int(r.quantity_target or 0) for r in runs)
    run_done = sum(int(r.quantity_completed or 0) for r in runs)
    tasks = db.query(Task).filter(Task.order_id == order.id).all()
    machine_ids = sorted({mid for mid in
                          [r.machine_id for r in runs] +
                          [t.machine_id for t in tasks]
                          if mid is not None}, key=str)
    machines = db.query(Machine).filter(Machine.id.in_(machine_ids)).all() if machine_ids else []
    machine_by_id = {m.id: m for m in machines}

    emp_names = _task_employee_names(db, tasks)
    task_items = [
        {"id": str(t.id), "name": t.name, "status": t.status, "progress": t.progress,
         "deadline": _iso(t.deadline),
         "employee_id": str(t.employee_id) if t.employee_id else None,
         "employee_name": emp_names.get(t.employee_id)}
        for t in tasks
    ]
    tasks_completed = [t for t in tasks if (t.status or "").upper() in CLOSED_TASK]
    tasks_open = [t for t in tasks if (t.status or "").upper() not in CLOSED_TASK]
    task_ids = {t.id for t in tasks}

    linked_incidents = db.query(Incident).filter(Incident.order_id == order.id).all()
    related_incidents = []
    if task_ids or machine_ids:
        q = db.query(Incident)
        if task_ids and machine_ids:
            from sqlalchemy import or_
            q = q.filter(or_(Incident.task_id.in_(list(task_ids)),
                             Incident.machine_id.in_(machine_ids)))
        elif task_ids:
            q = q.filter(Incident.task_id.in_(list(task_ids)))
        else:
            q = q.filter(Incident.machine_id.in_(machine_ids))
        for i in q.all():
            if i.order_id == order.id:
                continue  # already counted as explicitly linked
            via = []
            if i.task_id in task_ids:
                via.append("task")
            if i.machine_id in set(machine_ids):
                via.append("machine")
            if via:
                related_incidents.append((i, via))

    def _incident_dict(i, via=None):
        d = {"id": str(i.id), "incident_type": i.incident_type, "severity": i.severity,
             "status": i.status, "created_at": _iso(i.created_at),
             "machine_id": str(i.machine_id) if i.machine_id else None,
             "task_id": str(i.task_id) if i.task_id else None}
        if via is not None:
            d["via"] = via
        return d

    maint = (db.query(Maintenance).filter(Maintenance.machine_id.in_(machine_ids)).all()
             if machine_ids else [])

    recs = db.query(AIRecommendation).filter(AIRecommendation.entity_id == order.id).all()
    mems = db.query(FactoryMemory).filter(FactoryMemory.order_id == order.id).all()

    return {
        "order": {
            "id": str(order.id),
            "order_number": order.order_number,
            "customer_name": order.customer_name,
            "product": order.product,
            "quantity": order.quantity,
            "priority": order.priority,
            "status": order.status,
            "deadline": _iso(order.deadline),
            "created_at": _iso(order.created_at),
            "updated_at": _iso(order.updated_at),
            "is_final": is_final,
            "report_label": "Final Report" if is_final else "Order Report",
        },
        "production": {
            "runs": [
                {"id": str(r.id), "status": r.status,
                 "quantity_target": r.quantity_target, "quantity_completed": r.quantity_completed,
                 "machine_id": str(r.machine_id) if r.machine_id else None,
                 "task_id": str(r.task_id) if r.task_id else None,
                 "start_time": _iso(r.start_time),
                 "estimated_completion": _iso(r.estimated_completion)}
                for r in runs
            ],
            "run_count": len(runs),
            "target_quantity": run_target,
            "completed_quantity": run_done,
            "remaining_quantity": max(0, run_target - run_done),
        },
        "tasks": {
            "items": task_items,
            "total": len(tasks),
            "completed": len(tasks_completed),
            "open": len(tasks_open),
            "in_progress": sum(1 for t in tasks if (t.status or "").upper() == "IN_PROGRESS"),
        },
        "machines": {
            "used": [
                {"id": str(m.id), "name": m.name, "machine_code": m.machine_code,
                 "machine_type": m.machine_type, "department": m.department,
                 "criticality": m.criticality, "location": m.location,
                 "status": m.status, "health_status": m.health_status}
                for m in machines
            ],
            "count": len(machines),
        },
        "incidents": {
            "linked": [_incident_dict(i) for i in linked_incidents],
            "related": [_incident_dict(i, via) for i, via in related_incidents],
            "linked_count": len(linked_incidents),
            "related_count": len(related_incidents),
        },
        "maintenance": {
            "note": "machine-related maintenance for machines used by this order; not necessarily order-specific",
            "events": [
                {"id": str(mrow.id), "machine_id": str(mrow.machine_id) if mrow.machine_id else None,
                 "machine_name": machine_by_id.get(mrow.machine_id).name
                 if mrow.machine_id in machine_by_id else None,
                 "issue": mrow.issue, "status": mrow.status,
                 "maintenance_date": _iso(mrow.maintenance_date),
                 "created_at": _iso(mrow.created_at)}
                for mrow in maint
            ],
            "count": len(maint),
        },
        "ai": {
            "recommendations": [
                {"id": str(r.id), "recommendation_type": r.recommendation_type,
                 "recommendation": r.recommendation, "status": r.status,
                 "created_at": _iso(r.created_at)}
                for r in recs
            ],
            "memory": [
                {"id": str(mrow.id), "title": mrow.title, "event_type": mrow.event_type,
                 "created_at": _iso(mrow.created_at)}
                for mrow in mems
            ],
            "recommendation_count": len(recs),
            "memory_count": len(mems),
        },
        "summary": {
            "target_quantity": order.quantity,
            "completed_quantity": run_done,
            "remaining_quantity": max(0, (order.quantity or 0) - run_done),
            "run_count": len(runs),
            "tasks_total": len(tasks),
            "tasks_completed": len(tasks_completed),
            "tasks_open": len(tasks_open),
            "incidents_linked": len(linked_incidents),
            "incidents_related": len(related_incidents),
            "machines_used": len(machines),
            "maintenance_count": len(maint),
            "is_final": is_final,
        },
    }


@router.get("/weekly")
def weekly_report(week_offset: int = Query(0, ge=0, le=52), db: Session = Depends(get_db)):
    _require_scope(db)
    start, end = week_bounds(week_offset)
    out = build_weekly(db, start, end)
    out["week_start"] = start.isoformat()
    out["week_end"] = end.isoformat()
    return out


@router.get("/monthly")
def monthly_report(month: str = Query(...), db: Session = Depends(get_db)):
    _require_scope(db)
    start, end = month_bounds(month)
    out = build_period(db, start, end)
    out["month"] = month.strip()
    out["period_start"] = start.isoformat()
    out["period_end"] = end.isoformat()
    return out


@router.get("/orders/{order_id}")
def order_report(order_id: UUID, db: Session = Depends(get_db)):
    _require_scope(db)
    return build_order_report(db, order_id)
