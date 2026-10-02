"""Own notifications for the in-app bell (Phase 2). Prefix /notifications."""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from datetime import datetime

from backend.db.database import get_db
from backend.models.models import Notification
from backend.services.auth import get_current_user

router = APIRouter()


class NotificationResponse(BaseModel):
    id: UUID
    title: str
    body: Optional[str] = None
    link: Optional[str] = None
    kind: Optional[str] = None
    is_read: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


@router.get("", response_model=List[NotificationResponse])
def my_notifications(unread_only: bool = False, limit: int = 50, db: Session = Depends(get_db), user=Depends(get_current_user)):
    q = db.query(Notification).filter(Notification.user_id == user.id).order_by(Notification.created_at.desc())
    if unread_only:
        q = q.filter(Notification.is_read == False)  # noqa: E712
    return q.limit(min(limit, 200)).all()


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db), user=Depends(get_current_user)):
    n = db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read == False).count()  # noqa: E712
    return {"unread": n}


@router.post("/read-all")
def read_all(db: Session = Depends(get_db), user=Depends(get_current_user)):
    db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read == False).update({"is_read": True})  # noqa: E712
    db.commit()
    return {"ok": True}


@router.post("/{notif_id}/read", response_model=NotificationResponse)
def mark_read(notif_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    n = db.query(Notification).filter(Notification.id == notif_id, Notification.user_id == user.id).first()
    if n is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    n.is_read = True
    db.commit()
    db.refresh(n)
    return n
