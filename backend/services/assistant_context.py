"""Read-only factory snapshot for the AI Assistant chat (Phase 6).

Facts only: counts, machines with OPEN incidents, active orders with
deadlines/progress, recent incidents, pending AI recommendations, profile
industry. No telemetry dumps, no credentials, no full data files.
"""
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

from sqlalchemy.orm import Session

from backend.models.models import (
    AIRecommendation,
    Incident,
    Machine,
    Order,
    ProductionRun,
    Task,
)

CLOSED = ("COMPLETED", "DONE", "CANCELLED")


def _iso(v):
    try:
        return v.isoformat() if v is not None else None
    except Exception:
        return str(v)


def build_assistant_context(db: Session) -> Dict[str, Any]:
    machines = db.query(Machine).all()
    incidents = db.query(Incident).all()
    open_incs = [i for i in incidents if (i.status or "").upper() not in ("RESOLVED", "CLOSED")]
    orders = db.query(Order).all()
    active_orders = [o for o in orders if (o.status or "").upper() not in CLOSED]
    tasks = db.query(Task).all()
    open_tasks = [t for t in tasks if (t.status or "").upper() not in ("DONE", "COMPLETED", "CANCELLED")]
    runs = db.query(ProductionRun).all()
    pending_recs = (
        db.query(AIRecommendation).filter(AIRecommendation.status == "PENDING")
        .order_by(AIRecommendation.created_at.desc()).limit(10).all()
    )
    industry = None
    factory_name = None
    ai_preferences = None
    try:
        from backend.models.models import FactoryProfile
        from backend.services.factory import normalize_onboarding
        q = db.query(FactoryProfile)
        scope = db.info.get("factory_scope") if hasattr(db, "info") else None
        if scope:
            prof = q.filter(FactoryProfile.id == scope["uuid"]).first()
        else:
            prof = q.filter(FactoryProfile.status == "APPROVED").order_by(
                FactoryProfile.updated_at.desc()).first()
        if prof is not None:
            industry = prof.industry
            factory_name = prof.name
            sec = (normalize_onboarding(prof.onboarding).get("sections") or {}).get("ai_preferences") or {}
            ai_preferences = sec.get("data") or None
    except Exception:
        pass

    now = datetime.now(timezone.utc)

    def order_line(o):
        dl = None
        late = False
        if o.deadline:
            d = o.deadline if o.deadline.tzinfo else o.deadline.replace(tzinfo=timezone.utc)
            dl = d.isoformat()
            late = d < now
        return {"id": str(o.id), "order_number": o.order_number, "product": o.product,
                "quantity": o.quantity, "priority": o.priority, "status": o.status,
                "deadline": dl, "late": late, "progress": o.progress}

    return {
        "industry": industry,
        "factory_name": factory_name,
        "ai_preferences": ai_preferences,
        "counts": {
            "machines": len(machines), "open_incidents": len(open_incs),
            "active_orders": len(active_orders), "open_tasks": len(open_tasks),
            "production_runs": len(runs), "pending_recommendations": len(pending_recs),
        },
        "machines": [
            {"id": str(m.id), "name": m.name, "machine_type": m.machine_type,
             "status": m.status, "health_status": m.health_status,
             "open_incidents": sum(1 for i in open_incs if i.machine_id == m.id)}
            for m in machines
        ],
        "open_incidents": [
            {"id": str(i.id), "machine_id": str(i.machine_id) if i.machine_id else None,
             "severity": i.severity, "status": i.status,
             "description": (i.description or "")[:300], "created_at": _iso(i.created_at)}
            for i in sorted(open_incs, key=lambda x: x.created_at or now, reverse=True)[:10]
        ],
        "active_orders": [order_line(o) for o in active_orders[:20]],
        "open_tasks": [
            {"id": str(t.id), "name": t.name, "status": t.status,
             "required_skill": t.required_skill, "priority": t.priority,
             "employee_id": str(t.employee_id) if t.employee_id else None,
             "machine_id": str(t.machine_id) if t.machine_id else None,
             "order_id": str(t.order_id) if t.order_id else None}
            for t in open_tasks[:20]
        ],
        "pending_recommendations": [
            {"id": str(r.id), "recommendation_type": r.recommendation_type,
             "entity_type": r.entity_type, "entity_id": str(r.entity_id),
             "recommendation": (r.recommendation or "")[:300]}
            for r in pending_recs
        ],
    }
