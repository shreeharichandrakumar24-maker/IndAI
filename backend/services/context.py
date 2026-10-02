"""Deterministic incident context snapshot (Phase E).

build_incident_context() assembles ONLY facts from the DB: incident,
machine, latest + last ~30 readings summarized (min/max/avg/trend per
sensor), breaches vs thresholds, active production runs, linked tasks +
employee, affected orders, maintenance history, up to 5 similar past
factory_memory entries, profile terminology/industry.

Also computes the deterministic baseline risk per affected order
(LOW/MEDIUM/HIGH + the numbers used) which grounds the LLM and is
returned alongside the AI output.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from backend.models.models import (
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
from backend.services.abnormality import (
    ACTIVE_PRODUCTION_STATUSES,
    ACTIVE_TASK_STATUSES,
    evaluate_telemetry,
    resolve_thresholds,
)

HISTORY_LIMIT = 30


def _iso(v) -> Optional[str]:
    if v is None:
        return None
    try:
        return v.isoformat()
    except Exception:
        return str(v)


def _summarize(values: List[float]) -> Optional[Dict[str, Any]]:
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return None
    n = len(vals)
    avg = sum(vals) / n
    half = max(1, n // 2)
    first = sum(vals[:half]) / half
    last = sum(vals[-half:]) / half
    trend = "stable"
    if first != 0:
        drift = (last - first) / abs(first)
        if drift > 0.05:
            trend = "rising"
        elif drift < -0.05:
            trend = "falling"
    return {"min": min(vals), "max": max(vals), "avg": round(avg, 2), "trend": trend, "samples": n}


def deterministic_order_risk(remaining: int, hours_to_deadline: Optional[float], machine_down: bool) -> Dict[str, Any]:
    """Baseline risk from numbers only (backend-computed, not LLM)."""
    numbers = {
        "remaining_units": remaining,
        "hours_to_deadline": round(hours_to_deadline, 1) if hours_to_deadline is not None else None,
        "machine_down": machine_down,
    }
    if remaining <= 0:
        return {"risk_level": "LOW", "reason": "No remaining units on affected runs/orders.", "numbers": numbers}
    if machine_down and hours_to_deadline is not None and hours_to_deadline < 72:
        return {
            "risk_level": "HIGH",
            "reason": f"{remaining} units remaining with {numbers['hours_to_deadline']}h to deadline while the machine is down.",
            "numbers": numbers,
        }
    if remaining > 0 and (hours_to_deadline is None or hours_to_deadline < 168):
        return {
            "risk_level": "MEDIUM",
            "reason": f"{remaining} units remaining; deadline in {numbers['hours_to_deadline']}h." if hours_to_deadline is not None else f"{remaining} units remaining; no deadline set.",
            "numbers": numbers,
        }
    return {"risk_level": "LOW", "reason": "Remaining work fits comfortably before the deadline.", "numbers": numbers}


def build_incident_context(db: Session, incident_id: UUID) -> Dict[str, Any]:
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if inc is None:
        raise KeyError("Incident not found")

    machine = db.query(Machine).filter(Machine.id == inc.machine_id).first() if inc.machine_id else None
    thresholds = resolve_thresholds(machine.machine_type if machine else None, db)

    readings = []
    if inc.machine_id:
        readings = (
            db.query(MachineTelemetry)
            .filter(MachineTelemetry.machine_id == inc.machine_id)
            .order_by(MachineTelemetry.timestamp.desc())
            .limit(HISTORY_LIMIT)
            .all()
        )
    latest = readings[0] if readings else None
    chrono = list(reversed(readings))
    history_summary = {
        "count": len(readings),
        "temperature": _summarize([r.temperature for r in chrono]),
        "vibration": _summarize([r.vibration for r in chrono]),
        "current": _summarize([r.current for r in chrono]),
        "rpm": _summarize([r.rpm for r in chrono]),
    }
    breaches = evaluate_telemetry(latest, thresholds)["breaches"] if latest else []

    runs = []
    if inc.machine_id:
        runs = (
            db.query(ProductionRun)
            .filter(
                ProductionRun.machine_id == inc.machine_id,
                ProductionRun.status.in_(list(ACTIVE_PRODUCTION_STATUSES)),
            )
            .all()
        )
    # Also include runs directly tied to the incident's task/order for completeness.
    extra_runs = []
    if inc.task_id:
        extra_runs = db.query(ProductionRun).filter(ProductionRun.task_id == inc.task_id).all()
    run_ids = {r.id for r in runs}
    for r in extra_runs:
        if r.id not in run_ids:
            runs.append(r)
            run_ids.add(r.id)

    tasks = []
    if inc.machine_id:
        tasks = (
            db.query(Task)
            .filter(
                Task.machine_id == inc.machine_id,
                Task.status.in_(list(ACTIVE_TASK_STATUSES) + ["PENDING"]),
            )
            .limit(10)
            .all()
        )
    if inc.task_id and all(t.id != inc.task_id for t in tasks):
        t = db.query(Task).filter(Task.id == inc.task_id).first()
        if t:
            tasks.append(t)

    employee = None
    emp_ids = [t.employee_id for t in tasks if t.employee_id]
    if inc.employee_id:
        employee = db.query(Employee).filter(Employee.id == inc.employee_id).first()
    elif emp_ids:
        employee = db.query(Employee).filter(Employee.id == emp_ids[0]).first()

    order_ids = set()
    for r in runs:
        if r.order_id:
            order_ids.add(r.order_id)
    for t in tasks:
        if t.order_id:
            order_ids.add(t.order_id)
    if inc.order_id:
        order_ids.add(inc.order_id)
    orders = db.query(Order).filter(Order.id.in_(list(order_ids))).all() if order_ids else []

    maint = []
    if inc.machine_id:
        maint = (
            db.query(Maintenance)
            .filter(Maintenance.machine_id == inc.machine_id)
            .order_by(Maintenance.created_at.desc())
            .limit(10)
            .all()
        )

    similar = []
    if inc.machine_id:
        similar = (
            db.query(FactoryMemory)
            .filter(FactoryMemory.machine_id == inc.machine_id)
            .order_by(FactoryMemory.created_at.desc())
            .limit(5)
            .all()
        )

    now = datetime.now(timezone.utc)
    det_risk = []
    for o in orders:
        run_remaining = sum(
            max(0, (r.quantity_target or 0) - (r.quantity_completed or 0)) for r in runs if r.order_id == o.id
        )
        if run_remaining > 0:
            remaining = run_remaining
        else:
            remaining = max(0, int((o.quantity or 0) * (1 - (o.progress or 0))))
        hours = None
        if o.deadline:
            dl = o.deadline if o.deadline.tzinfo else o.deadline.replace(tzinfo=timezone.utc)
            hours = (dl - now).total_seconds() / 3600
        r = deterministic_order_risk(remaining, hours, machine_down=True)
        det_risk.append({
            "order_id": str(o.id),
            "order_number": o.order_number,
            "risk_level": r["risk_level"],
            "reason": r["reason"],
            "numbers": r["numbers"],
        })

    industry = None
    terminology = {"machine": "machine", "order": "order", "task": "task"}
    try:
        from backend.models.models import FactoryProfile
        prof = (
            db.query(FactoryProfile)
            .filter(FactoryProfile.status == "APPROVED")
            .order_by(FactoryProfile.updated_at.desc())
            .first()
        )
        if prof is not None:
            industry = prof.industry
            if isinstance(prof.profile, dict) and isinstance(prof.profile.get("terminology"), dict):
                terminology = {**terminology, **prof.profile["terminology"]}
    except Exception:
        pass

    return {
        "incident": {
            "id": str(inc.id), "incident_type": inc.incident_type, "severity": inc.severity,
            "status": inc.status, "description": inc.description, "created_at": _iso(inc.created_at),
            "machine_id": str(inc.machine_id) if inc.machine_id else None,
            "task_id": str(inc.task_id) if inc.task_id else None,
            "order_id": str(inc.order_id) if inc.order_id else None,
            "employee_id": str(inc.employee_id) if inc.employee_id else None,
        },
        "machine": (
            {"id": str(machine.id), "name": machine.name, "machine_type": machine.machine_type,
             "location": machine.location, "status": machine.status, "health_status": machine.health_status}
            if machine else None
        ),
        "thresholds": thresholds,
        "latest_reading": (
            {"temperature": latest.temperature, "vibration": latest.vibration, "current": latest.current,
             "rpm": latest.rpm, "machine_status": latest.machine_status, "timestamp": _iso(latest.timestamp)}
            if latest else None
        ),
        "history_summary": history_summary,
        "breaches": breaches,
        "production_runs": [
            {"id": str(r.id), "status": r.status, "quantity_target": r.quantity_target,
             "quantity_completed": r.quantity_completed,
             "remaining": max(0, (r.quantity_target or 0) - (r.quantity_completed or 0)),
             "estimated_completion": _iso(r.estimated_completion),
             "order_id": str(r.order_id) if r.order_id else None,
             "task_id": str(r.task_id) if r.task_id else None}
            for r in runs
        ],
        "tasks": [
            {"id": str(t.id), "name": t.name, "status": t.status, "required_skill": t.required_skill,
             "progress": t.progress, "deadline": _iso(t.deadline),
             "employee_id": str(t.employee_id) if t.employee_id else None,
             "order_id": str(t.order_id) if t.order_id else None}
            for t in tasks
        ],
        "employee": (
            {"id": str(employee.id), "name": employee.name, "role": employee.role,
             "skills": employee.skills, "shift": employee.shift, "availability": employee.availability}
            if employee else None
        ),
        "orders": [
            {"id": str(o.id), "order_number": o.order_number, "customer_name": o.customer_name,
             "product": o.product, "quantity": o.quantity, "priority": o.priority, "status": o.status,
             "deadline": _iso(o.deadline), "progress": o.progress}
            for o in orders
        ],
        "maintenance_history": [
            {"id": str(m.id), "issue": m.issue, "status": m.status, "technician": m.technician,
             "maintenance_date": _iso(m.maintenance_date), "resolution": m.resolution}
            for m in maint
        ],
        "similar_memory": [
            {"id": str(s.id), "title": s.title, "event_type": s.event_type,
             "description": (s.description or "")[:300], "resolution_action": s.resolution_action,
             "created_at": _iso(s.created_at)}
            for s in similar
        ],
        "deterministic_risk": det_risk,
        "industry": industry,
        "terminology": terminology,
    }
