"""What-if projector (Feature 9). Deterministic, display-only.

Three honest scenarios with genuinely recomputed numbers:
- DELAY_ORDER {order_id, days}: shifts the deadline, recomputes risk.
- RESOLVE_INCIDENT {incident_id}: assumes the incident resolved (machine no
  longer down), recomputes risk for orders touching that machine/order.
- REASSIGN_TASK {task_id, employee_id?, machine_id?}: feasibility verdict
  (skill/load/type/health) + risk recompute (dates honestly unchanged by a
  pure reassignment; shown as such).

Nothing here writes to the DB. Applying for real happens through the normal
endpoints from the frontend (approval gate intact).
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from backend.models.models import Employee, Incident, Machine, Order, Task
from backend.services.matcher import open_task_count, skills_of


def _order_numbers(db: Session, order_id: UUID):
    from backend.models.models import ProductionRun
    o = db.query(Order).filter(Order.id == order_id).first()
    if o is None:
        return None, None, None
    runs = db.query(ProductionRun).filter(ProductionRun.order_id == o.id).all()
    tasks = db.query(Task).filter(Task.order_id == o.id).all()
    remaining = sum(max(0, (r.quantity_target or 0) - (r.quantity_completed or 0)) for r in runs)
    if remaining <= 0:
        remaining = max(0, int((o.quantity or 0) * (1 - (o.progress or 0))))
    mids = {r.machine_id for r in runs if r.machine_id} | {t.machine_id for t in tasks if t.machine_id}
    return o, remaining, mids


def _risk_of(remaining: int, hours: Optional[float], down: bool) -> Dict[str, Any]:
    from backend.services.context import deterministic_order_risk
    r = deterministic_order_risk(remaining, hours, down)
    return {"risk_level": r["risk_level"], "reason": r["reason"], "numbers": r["numbers"]}


def _hours(deadline) -> Optional[float]:
    if not deadline:
        return None
    dl = deadline if deadline.tzinfo else deadline.replace(tzinfo=timezone.utc)
    return (dl - datetime.now(timezone.utc)).total_seconds() / 3600


def simulate_delay_order(db: Session, order_id: UUID, days: float) -> Dict[str, Any]:
    o, remaining, mids = _order_numbers(db, order_id)
    if o is None:
        raise KeyError("Order not found")
    open_incs = db.query(Incident).filter(
        Incident.status.in_(["OPEN", "IN_PROGRESS"])).all()
    down = {i.machine_id for i in open_incs if i.machine_id}
    blocked_direct = any(i.order_id == o.id for i in open_incs)
    is_down = blocked_direct or bool(mids & down)
    old = _risk_of(remaining, _hours(o.deadline), is_down)
    new_dl = (o.deadline if o.deadline else datetime.now(timezone.utc)) + timedelta(days=days)
    new = _risk_of(remaining, _hours(new_dl), is_down)
    return {
        "scenario": "DELAY_ORDER",
        "assumptions": [f"Deadline moved {days:+g} days; work remaining and machine state unchanged."],
        "affected_orders": [{
            "order_id": str(o.id), "order_number": o.order_number,
            "old_risk": old["risk_level"], "new_risk": new["risk_level"],
            "old_reason": old["reason"], "new_reason": new["reason"],
            "new_deadline": new_dl.isoformat(),
            "delta_hours": round((_hours(new_dl) or 0) - (_hours(o.deadline) or 0), 1),
        }],
        "warnings": [] if o.deadline else ["Order has no deadline; projection assumes today as baseline."],
    }


def simulate_resolve_incident(db: Session, incident_id: UUID) -> Dict[str, Any]:
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if inc is None:
        raise KeyError("Incident not found")
    open_incs = [i for i in db.query(Incident).filter(
        Incident.status.in_(["OPEN", "IN_PROGRESS"])).all() if i.id != inc.id]
    down = {i.machine_id for i in open_incs if i.machine_id}
    affected = []
    orders = db.query(Order).all()
    for o in orders:
        linked = (inc.order_id is not None and o.id == inc.order_id) or any(
            (t.order_id == o.id and t.machine_id == inc.machine_id)
            for t in db.query(Task).filter(Task.machine_id == inc.machine_id).all()
        ) if inc.machine_id else (inc.order_id is not None and o.id == inc.order_id)
        if not linked:
            continue
        from backend.models.models import ProductionRun
        runs = db.query(ProductionRun).filter(ProductionRun.order_id == o.id).all()
        remaining = sum(max(0, (r.quantity_target or 0) - (r.quantity_completed or 0)) for r in runs)
        if remaining <= 0:
            remaining = max(0, int((o.quantity or 0) * (1 - (o.progress or 0))))
        mids = {r.machine_id for r in runs if r.machine_id}
        was_down = (inc.machine_id in mids) or (inc.order_id == o.id)
        old = _risk_of(remaining, _hours(o.deadline), was_down)
        new = _risk_of(remaining, _hours(o.deadline), False)
        affected.append({
            "order_id": str(o.id), "order_number": o.order_number,
            "old_risk": old["risk_level"], "new_risk": new["risk_level"],
            "old_reason": old["reason"], "new_reason": new["reason"],
            "new_deadline": o.deadline.isoformat() if o.deadline else None,
            "delta_hours": 0.0,
        })
    return {
        "scenario": "RESOLVE_INCIDENT",
        "assumptions": ["Incident resolved; machine back up; no other changes."],
        "affected_orders": affected,
        "warnings": [] if affected else ["No orders linked to this incident; nothing would change."],
    }


def simulate_reassign_task(db: Session, task_id: UUID, employee_id: Optional[UUID] = None,
                           machine_id: Optional[UUID] = None) -> Dict[str, Any]:
    t = db.query(Task).filter(Task.id == task_id).first()
    if t is None:
        raise KeyError("Task not found")
    verdicts = []
    ok = True
    emp = None
    mac = None
    if employee_id:
        emp = db.query(Employee).filter(Employee.id == employee_id).first()
        if emp is None:
            raise KeyError("Employee not found")
        if (emp.status or "ACTIVE").upper() != "ACTIVE" or (emp.availability or "AVAILABLE").upper() != "AVAILABLE":
            verdicts.append(f"{emp.name} is not AVAILABLE.")
            ok = False
        else:
            from backend.services.matcher import _skill_match
            if not _skill_match(skills_of(emp), t.required_skill or ""):
                verdicts.append(f"{emp.name} lacks skill '{t.required_skill}'.")
                ok = False
            else:
                verdicts.append(f"{emp.name} has the skill; {open_task_count(db, emp.id)} open task(s).")
    if machine_id:
        mac = db.query(Machine).filter(Machine.id == machine_id).first()
        if mac is None:
            raise KeyError("Machine not found")
        if (mac.status or "OPERATIONAL").upper() != "OPERATIONAL":
            verdicts.append(f"{mac.name} is not OPERATIONAL.")
            ok = False
        elif t.required_skill and mac.machine_type and t.required_skill.lower() not in (mac.machine_type or "").lower() \
                and mac.machine_type.lower() not in (t.required_skill or "").lower():
            verdicts.append(f"Note: task skill '{t.required_skill}' vs machine type '{mac.machine_type}'.")
        else:
            verdicts.append(f"{mac.name} is OPERATIONAL ({mac.health_status or 'GOOD'}).")
    o, remaining, mids = (None, 0, set())
    if t.order_id:
        o, remaining, mids = _order_numbers(db, t.order_id)
    risk_note = "Dates unchanged by reassignment alone."
    affected = []
    if o is not None:
        old = _risk_of(remaining, _hours(o.deadline), False)
        affected.append({
            "order_id": str(o.id), "order_number": o.order_number,
            "old_risk": old["risk_level"], "new_risk": old["risk_level"],
            "old_reason": old["reason"], "new_reason": risk_note,
            "new_deadline": o.deadline.isoformat() if o.deadline else None,
            "delta_hours": 0.0,
        })
    return {
        "scenario": "REASSIGN_TASK",
        "assumptions": ["Only the assignment changes; dates, scope and machine state unchanged."],
        "affected_orders": affected,
        "warnings": [],
        "feasibility": {"ok": ok, "verdicts": verdicts,
                        "employee_id": str(emp.id) if emp else None,
                        "machine_id": str(mac.id) if mac else None},
    }
