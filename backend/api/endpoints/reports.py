"""Weekly operations report (Phase 5). Prefix /reports.

Deterministic aggregates only — no LLM. build_weekly() is a pure function
of the DB session + week bounds so it can be unit-tested without HTTP.
Weeks are Monday 00:00 -> Sunday 23:59:59 UTC; ?week_offset=0 is this week.
"""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.models.models import (
    AIRecommendation,
    FactoryMemory,
    Incident,
    Machine,
    Order,
)

router = APIRouter()

CLOSED_ORDER = ("COMPLETED", "DONE", "CANCELLED")
ACTIVE_INCIDENT = ("OPEN", "IN_PROGRESS")


def week_bounds(offset: int = 0):
    now = datetime.now(timezone.utc)
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    start = monday - timedelta(weeks=offset)
    return start, start + timedelta(days=7) - timedelta(seconds=1)


def _code(name: str) -> str:
    import re
    m = re.match(r"^(M-\d{3})", (name or "").strip())
    return m.group(1) if m else (name or "")[:12]


def build_weekly(db: Session, start: datetime, end: datetime) -> dict:
    orders = db.query(Order).all()
    completed = [o for o in orders if (o.status or "").upper() in CLOSED_ORDER]
    completed_this_week = [o for o in completed if o.updated_at and start <= o.updated_at.replace(tzinfo=timezone.utc) <= end]
    now = datetime.now(timezone.utc)
    late = []
    for o in orders:
        if (o.status or "").upper() in CLOSED_ORDER or not o.deadline:
            continue
        dl = o.deadline if o.deadline.tzinfo else o.deadline.replace(tzinfo=timezone.utc)
        if dl < now:
            late.append(o)

    incidents = db.query(Incident).all()
    raised = [i for i in incidents if i.created_at and start <= i.created_at.replace(tzinfo=timezone.utc) <= end]
    currently_open = [i for i in incidents if (i.status or "").upper() in ACTIVE_INCIDENT]

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
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "orders": {
            "completed_this_week": len(completed_this_week),
            "late_now": len(late),
            "late_orders": [
                {"order_number": o.order_number, "deadline": o.deadline.isoformat() if o.deadline else None,
                 "status": o.status} for o in late[:20]
            ],
            "active_total": sum(1 for o in orders if (o.status or "").upper() not in CLOSED_ORDER),
        },
        "downtime": {
            "incidents_raised_this_week": len(raised),
            "currently_open": len(currently_open),
        },
        "top_failing_machines": top_failing,
        "decisions": {
            "admin_decisions_this_week": len(decisions),
            "recommendations_approved": approved,
            "recommendations_rejected": rejected,
        },
    }


@router.get("/weekly")
def weekly_report(week_offset: int = Query(0, ge=0, le=52), db: Session = Depends(get_db)):
    start, end = week_bounds(week_offset)
    return build_weekly(db, start, end)
