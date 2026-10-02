"""Deterministic notification triggers (Phase 2).

Plain-language rows for the in-app bell. Called from incident creation and
the analysis endpoint — never from the LLM. Failures here must never break
the calling workflow, so every helper swallows its own errors.
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session


def _recipients(db: Session, roles=("MANAGER", "OPERATOR")) -> List:
    from backend.models.models import AppUser
    try:
        return (
            db.query(AppUser)
            .filter(AppUser.active == True, AppUser.role.in_(list(roles)))  # noqa: E712
            .all()
        )
    except Exception:
        return []


def _add(db: Session, user_id: UUID, title: str, body: str = "", link: str = "", kind: str = ""):
    from backend.models.models import Notification
    try:
        db.add(Notification(user_id=user_id, title=title, body=body, link=link, kind=kind))
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


def notify_incident(db: Session, machine_name: str, severity: str, incident_id: UUID):
    """New OPEN incident -> bell for managers + operators, plain language."""
    try:
        code = (machine_name or "A machine").split(" · ")[0]
        title = f"Machine {code} needs attention ({severity})"
        body = f"Abnormal readings on {machine_name}. Open the incident to inspect and schedule repair."
        for u in _recipients(db):
            _add(db, u.id, title, body, link="incidents", kind="INCIDENT_OPENED")
    except Exception:
        pass


def notify_order_risk(db: Session, order_number: str, risk: dict):
    """HIGH deterministic order risk -> bell. risk = deterministic_order_risk()."""
    try:
        if (risk or {}).get("risk_level") != "HIGH":
            return
        title = f"Order {order_number} is at high risk"
        body = (risk.get("reason") or "") + " Check the incident analysis for details."
        for u in _recipients(db):
            _add(db, u.id, title, body, link="incidents", kind="ORDER_AT_RISK")
    except Exception:
        pass


def notify_approvals(db: Session, count: int):
    """New AI recommendations waiting -> bell for managers only."""
    try:
        if count <= 0:
            return
        title = f"{count} recommendation{'s' if count != 1 else ''} need{'s' if count == 1 else ''} your approval"
        body = "AI analysis produced new recommendations. Review and approve or reject them."
        for u in _recipients(db, roles=("MANAGER",)):
            _add(db, u.id, title, body, link="incidents", kind="APPROVAL_NEEDED")
    except Exception:
        pass
