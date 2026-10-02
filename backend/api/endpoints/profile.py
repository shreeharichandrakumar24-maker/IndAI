"""Factory profile endpoints (Phase A6). Prefix /profile."""
import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import ProgrammingError

from backend.db.database import get_db
from backend.models.models import FactoryProfile, Machine
from backend.schemas.profile import (
    FactoryProfileData,
    FactoryProfileResponse,
    GenerateRequest,
)
from backend.services.factory_preset import CNC_PRESET, get_preset
from backend.services.llm import LLMUnavailable, complete_json

router = APIRouter()

MIGRATION_HINT = "factory_profile table missing — run backend/db/migrations/001_factory_profile.sql in Supabase first."

PROFILE_SYSTEM_PROMPT = """You configure a small mechanical/hardware factory.
Given the admin's onboarding answers, output a factory profile as JSON with keys:
industry (string), description (string),
terminology {machine, order, task} (short singular nouns),
machines[] {code like M-001, name starting with that code, machine_type, location, sensors subset of [temperature, vibration, current, rpm]},
thresholds {<machine_type>: {temp_max, vibration_max, current_max, rpm_min}} (numbers only),
task_templates[] {name, description, required_skill, machine_type, typical_order},
skills[] (strings), certifications[] (strings), shifts[] (strings), main_problems[] (strings).
Keep the 8 canonical machines M-001..M-008 when the answers mention CNC/mechanical or nothing specific.
Use conservative alert limits near temp_max 85, vibration_max 5, current_max 10, rpm_min 1300.
Output JSON ONLY."""


def _row_to_response(row: FactoryProfile, source: Optional[str] = None) -> dict:
    profile = row.profile if isinstance(row.profile, dict) else {}
    if not source:
        source = profile.get("_source", "preset") if isinstance(profile, dict) else "preset"
    return {
        "id": str(row.id),
        "industry": row.industry,
        "status": row.status,
        "answers": row.answers,
        "profile": profile,
        "source": source,
    }


def _get_single(db: Session) -> Optional[FactoryProfile]:
    try:
        return db.query(FactoryProfile).order_by(FactoryProfile.updated_at.desc()).first()
    except ProgrammingError:
        raise HTTPException(status_code=500, detail=MIGRATION_HINT)


def _code_of(name: str) -> Optional[str]:
    m = re.match(r"^(M-\d{3})", (name or "").strip())
    return m.group(1) if m else None


@router.get("", response_model=FactoryProfileResponse)
def get_profile(db: Session = Depends(get_db)):
    row = _get_single(db)
    if row is None:
        raise HTTPException(status_code=404, detail="No factory profile yet. POST /profile/generate first.")
    return _row_to_response(row)


@router.get("/preset")
def get_preset_profile():
    return {"source": "preset", "profile": CNC_PRESET}


@router.post("/generate", response_model=FactoryProfileResponse)
def generate_profile(body: GenerateRequest, db: Session = Depends(get_db)):
    answers = body.answers.model_dump()
    try:
        draft = complete_json(PROFILE_SYSTEM_PROMPT, {"answers": answers}, FactoryProfileData)
        draft = draft.sanitized()
        source = "ai"
        profile_dict = draft.model_dump()
    except LLMUnavailable:
        draft = get_preset()
        source = "preset"
        profile_dict = draft.model_dump()
    profile_dict["_source"] = source
    industry = profile_dict.get("industry") or (answers.get("industry") or "CNC / Mechanical")
    try:
        row = _get_single(db)
        if row is None:
            row = FactoryProfile(industry=industry, status="DRAFT", answers=answers, profile=profile_dict)
            db.add(row)
        else:
            row.industry = industry
            row.status = "DRAFT"
            row.answers = answers
            row.profile = profile_dict
        db.commit()
        db.refresh(row)
    except ProgrammingError:
        raise HTTPException(status_code=500, detail=MIGRATION_HINT)
    return _row_to_response(row, source=source)


@router.put("", response_model=FactoryProfileResponse)
def save_profile(body: dict, db: Session = Depends(get_db)):
    """Save an edited draft. Body may be the full profile JSON or {profile: {...}}."""
    raw = body.get("profile", body) if isinstance(body, dict) else {}
    try:
        validated = FactoryProfileData.model_validate(raw).sanitized()
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid profile JSON: {e}")
    profile_dict = validated.model_dump()
    # Preserve source flag if present.
    if isinstance(raw, dict) and raw.get("_source") in ("ai", "preset"):
        profile_dict["_source"] = raw["_source"]
    try:
        row = _get_single(db)
        if row is None:
            row = FactoryProfile(
                industry=profile_dict.get("industry", "CNC / Mechanical"),
                status="DRAFT",
                answers={},
                profile=profile_dict,
            )
            db.add(row)
        else:
            row.industry = profile_dict.get("industry", row.industry)
            row.profile = profile_dict
            if row.status != "APPROVED":
                row.status = "DRAFT"
        db.commit()
        db.refresh(row)
    except ProgrammingError:
        raise HTTPException(status_code=500, detail=MIGRATION_HINT)
    return _row_to_response(row)


@router.post("/approve", response_model=FactoryProfileResponse)
def approve_profile(db: Session = Depends(get_db)):
    try:
        row = _get_single(db)
        if row is None:
            raise HTTPException(status_code=404, detail="No factory profile to approve.")
        try:
            data = FactoryProfileData.model_validate(row.profile or {}).sanitized()
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Stored profile invalid, re-generate: {e}")
        row.status = "APPROVED"
        row.industry = data.industry
        # Idempotent seed: match by stable code prefix (M-001..) or full name; never duplicate.
        existing = db.query(Machine).all()
        seen_codes = {_code_of(m.name) for m in existing}
        seen_names = {m.name for m in existing}
        created = 0
        skipped = 0
        for pm in data.machines:
            if pm.code in seen_codes or pm.name in seen_names:
                skipped += 1
                continue
            db.add(Machine(name=pm.name, machine_type=pm.machine_type, location=pm.location or "", status="OPERATIONAL", health_status="GOOD"))
            seen_codes.add(pm.code)
            seen_names.add(pm.name)
            created += 1
        db.commit()
        db.refresh(row)
        resp = _row_to_response(row)
        resp["seed"] = {"created": created, "skipped": skipped}
        return resp
    except ProgrammingError:
        raise HTTPException(status_code=500, detail=MIGRATION_HINT)
