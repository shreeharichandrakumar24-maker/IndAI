"""User admin endpoints (Phase 1). Prefix /users. Manager-only except /me."""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from datetime import datetime

from backend.db.database import get_db
from backend.models.models import AppUser
from backend.services.auth import ROLES, get_current_user, require_manager

router = APIRouter()


class UserResponse(BaseModel):
    id: UUID
    email: Optional[str] = None
    name: Optional[str] = None
    role: str
    employee_id: Optional[UUID] = None
    active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RoleBody(BaseModel):
    role: str


class UserUpdateBody(BaseModel):
    name: Optional[str] = None
    employee_id: Optional[UUID] = None
    active: Optional[bool] = None


@router.get("/me", response_model=UserResponse)
def me(user=Depends(get_current_user)):
    return user


@router.get("", response_model=List[UserResponse])
def list_users(db: Session = Depends(get_db), _m=Depends(require_manager)):
    return db.query(AppUser).order_by(AppUser.created_at).all()


@router.put("/{user_id}/role", response_model=UserResponse)
def set_role(user_id: UUID, body: RoleBody, db: Session = Depends(get_db), _m=Depends(require_manager)):
    role = (body.role or "").upper()
    if role not in ROLES:
        raise HTTPException(status_code=422, detail=f"Unknown role '{body.role}'. Use {list(ROLES)}.")
    u = db.query(AppUser).filter(AppUser.id == user_id).first()
    if u is None:
        raise HTTPException(status_code=404, detail="User not found")
    if u.role == "MANAGER" and role != "MANAGER":
        others = db.query(AppUser).filter(AppUser.role == "MANAGER", AppUser.active == True, AppUser.id != u.id).count()
        if others == 0:
            raise HTTPException(status_code=422, detail="Cannot demote the last active manager.")
    u.role = role
    db.commit()
    db.refresh(u)
    return u


@router.put("/{user_id}", response_model=UserResponse)
def update_user(user_id: UUID, body: UserUpdateBody, db: Session = Depends(get_db), _m=Depends(require_manager)):
    u = db.query(AppUser).filter(AppUser.id == user_id).first()
    if u is None:
        raise HTTPException(status_code=404, detail="User not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("active") is False:
        u2 = db.query(AppUser).filter(AppUser.id == user_id).first()
        if u2.role == "MANAGER":
            others = db.query(AppUser).filter(AppUser.role == "MANAGER", AppUser.active == True, AppUser.id != u2.id).count()
            if others == 0:
                raise HTTPException(status_code=422, detail="Cannot deactivate the last active manager.")
    for k, v in data.items():
        setattr(u, k, v)
    db.commit()
    db.refresh(u)
    return u
