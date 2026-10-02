"""Predictive order-risk engine (Feature 8).

Deterministic first: remaining work vs deadline vs machine-down status,
computed live from current rows (no stored risk table to go stale).
Optional AI layer adds delay-hour estimates + plain reasons when asked
(?ai=true) and the LLM key exists; otherwise estimates are null and the
source is labeled deterministic.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.models.models import Incident, Order, ProductionRun, Task

CLOSED_ORDER = ("COMPLETED", "DONE", "CANCELLED")
OPEN_INCIDENT = ("OPEN", "IN_PROGRESS")


def _hours_to(deadline) -> Optional[float]:
    if not deadline:
        return None
    dl = deadline if deadline.tzinfo else deadline.replace(tzinfo=timezone.utc)
    return (dl - datetime.now(timezone.utc)).total_seconds() / 3600


def compute_order_risks(db: Session) -> List[Dict[str, Any]]:
    """One risk row per active order. Pure function of the DB. Never throws."""
    from backend.services.context import deterministic_order_risk

    orders = db.query(Order).all()
    runs = db.query(ProductionRun).all()
    tasks = db.query(Task).all()
    open_incs = db.query(Incident).filter(Incident.status.in_(list(OPEN_INCIDENT))).all()
    down_machines = {i.machine_id for i in open_incs if i.machine_id}

    runs_by_order: Dict[Any, List] = {}
    for r in runs:
        if r.order_id:
            runs_by_order.setdefault(r.order_id, []).append(r)
    tasks_by_order: Dict[Any, List] = {}
    for t in tasks:
        if t.order_id:
            tasks_by_order.setdefault(t.order_id, []).append(t)

    out = []
    for o in orders:
        if (o.status or "").upper() in CLOSED_ORDER:
            continue
        oruns = runs_by_order.get(o.id, [])
        remaining = sum(max(0, (r.quantity_target or 0) - (r.quantity_completed or 0)) for r in oruns)
        if remaining <= 0:
            remaining = max(0, int((o.quantity or 0) * (1 - (o.progress or 0))))
        mids = {r.machine_id for r in oruns if r.machine_id}
        mids |= {t.machine_id for t in tasks_by_order.get(o.id, []) if t.machine_id}
        # Incident linked directly to the order also counts as blocked.
        blocked_directly = any(i.order_id == o.id for i in open_incs)
        machine_down = blocked_directly or bool(mids & down_machines)
        hours = _hours_to(o.deadline)
        r = deterministic_order_risk(remaining, hours, machine_down)
        out.append({
            "order_id": str(o.id),
            "order_number": o.order_number,
            "product": o.product,
            "status": o.status,
            "priority": o.priority,
            "deadline": o.deadline.isoformat() if o.deadline else None,
            "progress": o.progress,
            "risk_level": r["risk_level"],
            "reason": r["reason"],
            "numbers": r["numbers"],
            "machine_down": machine_down,
            "estimated_delay_hours": None,
            "ai_reason": None,
        })
    severity = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    out.sort(key=lambda x: (severity.get(x["risk_level"], 3), x["order_number"] or ""))
    return out
