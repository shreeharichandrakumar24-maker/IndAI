"""Company / factory registry endpoints (Part 1 + 8).

Reuses the existing ``factory_profile`` table as the company list — no new
Factory/Company model is created. Reads/writes here are intentionally NOT
factory-scoped (you must be able to see every company to pick one).
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.db.scoping import SCOPE_KEY
from backend.models.models import FactoryProfile
from backend.services.factory import (
    INDUSTRY_OPTIONS,
    default_onboarding,
    ensure_default_factory,
    factory_summary,
    normalize_onboarding,
)

router = APIRouter()

MIGRATION_HINT = (
    "factory_profile columns missing — run backend/db/migrations/008_multi_factory.sql "
    "in Supabase first."
)


class FactoryCreate(BaseModel):
    name: str
    industry: Optional[str] = None


class FactoryUpdate(BaseModel):
    name: Optional[str] = None
    industry: Optional[str] = None


@router.get("")
def list_factories(db: Session = Depends(get_db)):
    """Every company/factory the demo can enter, with setup status + counts."""
    db.info.pop(SCOPE_KEY, None)  # listing must never be scoped
    try:
        ensure_default_factory(db)
        rows = db.query(FactoryProfile).order_by(FactoryProfile.is_default.desc(), FactoryProfile.created_at.asc()).all()
        return {
            "factories": [factory_summary(db, r) for r in rows],
            "industries": INDUSTRY_OPTIONS,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{MIGRATION_HINT} ({e})")


@router.post("")
def create_factory(body: FactoryCreate, db: Session = Depends(get_db)):
    """Create a new company/factory in DRAFT (onboarding incomplete)."""
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Company / factory name is required.")
    try:
        row = FactoryProfile(
            name=name,
            industry=(body.industry or "").strip() or None,
            status="DRAFT",
            answers={},
            profile={},
            onboarding=default_onboarding(name),
            is_default=False,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{MIGRATION_HINT} ({e})")
    db.info.pop(SCOPE_KEY, None)
    return factory_summary(db, row)


@router.get("/{factory_id}")
def get_factory(factory_id: UUID, db: Session = Depends(get_db)):
    db.info.pop(SCOPE_KEY, None)
    row = db.query(FactoryProfile).filter(FactoryProfile.id == factory_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Factory not found.")
    summary = factory_summary(db, row)
    summary["onboarding"] = normalize_onboarding(row.onboarding)
    summary["profile"] = row.profile if isinstance(row.profile, dict) else {}
    return summary


@router.put("/{factory_id}")
def update_factory(factory_id: UUID, body: FactoryUpdate, db: Session = Depends(get_db)):
    db.info.pop(SCOPE_KEY, None)
    row = db.query(FactoryProfile).filter(FactoryProfile.id == factory_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Factory not found.")
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Name cannot be blank.")
        row.name = name
    if body.industry is not None:
        row.industry = body.industry.strip() or row.industry
    db.commit()
    db.refresh(row)
    return factory_summary(db, row)
