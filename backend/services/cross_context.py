"""Cross-system scope snapshot for Feature 7 root-cause analysis.

Unlike incident context (one incident), this joins every system around a
scope: one machine and/or one order. Facts only — the LLM correlates.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from backend.models.models import (
    FactoryMemory,
    Incident,
    Machine,
    MachineTelemetry,
    Maintenance,
    Order,
    ProductionRun,
    Task,
)
from backend.services.abnormality import evaluate_telemetry, resolve_thresholds
from backend.services.context import _iso, _summarize

HISTORY_LIMIT = 30
ACTIVE_TASK = ("PENDING", "IN_PROGRESS", "PLANNED")
OPEN_INCIDENT = ("OPEN", "IN_PROGRESS")


def build_cross_context(db: Session, machine_id: Optional[UUID] = None,
                        order_id: Optional[UUID] = None) -> Dict[str, Any]:
    if machine_id is None and order_id is None:
        raise KeyError("Provide machine_id or order_id.")

    machine = db.query(Machine).filter(Machine.id == machine_id).first() if machine_id else None
    order = db.query(Order).filter(Order.id == order_id).first() if order_id else None
    if machine_id and machine is None:
        raise KeyError("Machine not found")
    if order_id and order is None:
        raise KeyError("Order not found")

    machine_ids = {machine.id} if machine else set()
    order_ids = {order.id} if order else set()

    # Expand scope: tasks/runs touching the given machine or order.
    tasks = []
    if machine:
        tasks += db.query(Task).filter(Task.machine_id == machine.id).limit(50).all()
    if order:
        tasks += [t for t in db.query(Task).filter(Task.order_id == order.id).limit(50).all()
                  if t.id not in {x.id for x in tasks}]
    for t in tasks:
        if t.order_id:
            order_ids.add(t.order_id)
        if t.machine_id:
            machine_ids.add(t.machine_id)
    runs = []
    if machine:
        runs += db.query(ProductionRun).filter(ProductionRun.machine_id == machine.id).limit(50).all()
    if order:
        runs += [r for r in db.query(ProductionRun).filter(ProductionRun.order_id == order.id).limit(50).all()
                 if r.id not in {x.id for x in runs}]

    telemetry_summary = {}
    breaches_by_machine = {}
    thresholds_by_machine = {}
    for mid in list(machine_ids):
        m = db.query(Machine).filter(Machine.id == mid).first()
        if m is None:
            continue
        th = resolve_thresholds(m.machine_type, db)
        thresholds_by_machine[str(mid)] = th
        rows = (
            db.query(MachineTelemetry).filter(MachineTelemetry.machine_id == mid)
            .order_by(MachineTelemetry.timestamp.desc()).limit(HISTORY_LIMIT).all()
        )
        chrono = list(reversed(rows))
        telemetry_summary[str(mid)] = {
            "count": len(rows),
            "temperature": _summarize([r.temperature for r in chrono]),
            "vibration": _summarize([r.vibration for r in chrono]),
            "current": _summarize([r.current for r in chrono]),
            "rpm": _summarize([r.rpm for r in chrono]),
        }
        if rows:
            breaches_by_machine[str(mid)] = evaluate_telemetry(rows[0], th)["breaches"]

    incidents = []
    if machine_ids or order_ids:
        q = db.query(Incident)
        conds = []
        if machine_ids:
            conds.append(Incident.machine_id.in_(list(machine_ids)))
        if order_ids:
            conds.append(Incident.order_id.in_(list(order_ids)))
        from sqlalchemy import or_
        incidents = q.filter(or_(*conds)).order_by(Incident.created_at.desc()).limit(20).all()

    maintenance = []
    for mid in list(machine_ids):
        maintenance += (
            db.query(Maintenance).filter(Maintenance.machine_id == mid)
            .order_by(Maintenance.created_at.desc()).limit(10).all()
        )

    memories = []
    for mid in list(machine_ids):
        memories += (
            db.query(FactoryMemory).filter(FactoryMemory.machine_id == mid)
            .order_by(FactoryMemory.created_at.desc()).limit(5).all()
        )
    for oid in list(order_ids):
        memories += (
            db.query(FactoryMemory).filter(FactoryMemory.order_id == oid)
            .order_by(FactoryMemory.created_at.desc()).limit(5).all()
        )

    all_machines = [db.query(Machine).filter(Machine.id == mid).first() for mid in machine_ids]
    all_orders = [db.query(Order).filter(Order.id == oid).first() for oid in order_ids]

    return {
        "scope": {"machine_id": str(machine_id) if machine_id else None,
                  "order_id": str(order_id) if order_id else None},
        "machines": [
            {"id": str(m.id), "name": m.name, "machine_type": m.machine_type,
             "status": m.status, "health_status": m.health_status}
            for m in all_machines if m is not None
        ],
        "orders": [
            {"id": str(o.id), "order_number": o.order_number, "product": o.product,
             "quantity": o.quantity, "priority": o.priority, "status": o.status,
             "deadline": _iso(o.deadline), "progress": o.progress}
            for o in all_orders if o is not None
        ],
        "telemetry_summary": telemetry_summary,
        "thresholds": thresholds_by_machine,
        "current_breaches": breaches_by_machine,
        "tasks": [
            {"id": str(t.id), "name": t.name, "status": t.status,
             "required_skill": t.required_skill, "progress": t.progress,
             "employee_id": str(t.employee_id) if t.employee_id else None,
             "machine_id": str(t.machine_id) if t.machine_id else None,
             "order_id": str(t.order_id) if t.order_id else None}
            for t in tasks[:30]
        ],
        "production_runs": [
            {"id": str(r.id), "status": r.status,
             "quantity_target": r.quantity_target, "quantity_completed": r.quantity_completed,
             "order_id": str(r.order_id) if r.order_id else None,
             "machine_id": str(r.machine_id) if r.machine_id else None}
            for r in runs[:30]
        ],
        "incidents": [
            {"id": str(i.id), "incident_type": i.incident_type, "severity": i.severity,
             "status": i.status, "description": (i.description or "")[:300],
             "machine_id": str(i.machine_id) if i.machine_id else None,
             "order_id": str(i.order_id) if i.order_id else None,
             "created_at": _iso(i.created_at)}
            for i in incidents
        ],
        "maintenance_history": [
            {"id": str(m.id), "issue": m.issue, "status": m.status,
             "technician": m.technician, "maintenance_date": _iso(m.maintenance_date)}
            for m in maintenance[:15]
        ],
        "similar_memory": [
            {"id": str(s.id), "title": s.title, "event_type": s.event_type,
             "description": (s.description or "")[:300],
             "resolution_action": (s.resolution_action or "")[:300]}
            for s in memories[:10]
        ],
    }
