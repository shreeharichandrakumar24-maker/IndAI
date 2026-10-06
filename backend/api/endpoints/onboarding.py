"""8-step factory onboarding endpoints (Parts 3 + 4 + 5).

Scoped to the currently selected factory via the ``X-Factory-Id`` header
(set by the frontend). All operational writes reuse the EXISTING tables
(employees / machines / orders / maintenance) — nothing is duplicated and
legacy rows are never touched. Onboarding progress lives in
``factory_profile.onboarding`` (JSONB) so a browser refresh loses nothing.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.db.scoping import SCOPE_KEY
from backend.models.models import (
    Employee,
    FactoryProfile,
    Machine,
    Maintenance,
    Order,
)
from backend.services.factory import (
    DEFAULT_AI_PREFERENCES,
    DEFAULT_THRESHOLDS,
    REQUIRED_SECTIONS,
    SECTION_AVAILABLE,
    SECTION_DEFAULT,
    SECTION_NOT_AVAILABLE,
    SECTION_PENDING,
    STEP_KEYS,
    STATUS_COMPLETE,
    STATUS_IN_PROGRESS,
    factory_setup_complete,
    factory_summary,
    normalize_onboarding,
    parse_csv,
    profile_thresholds_from_onboarding,
    validate_ai_preferences,
    validate_company,
    validate_employee_rows,
    validate_maintenance_rows,
    validate_machine_rows,
    validate_order_rows,
    validate_production,
    validate_thresholds,
)

router = APIRouter()

LIST_SECTIONS = ("employees", "machines", "orders", "maintenance")


def _factory(db: Session) -> FactoryProfile:
    scope = db.info.get(SCOPE_KEY)
    if not scope:
        raise HTTPException(status_code=400, detail="No active factory. Send the X-Factory-Id header.")
    row = db.query(FactoryProfile).filter(FactoryProfile.id == scope["uuid"]).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Factory not found.")
    return row


def _state(row: FactoryProfile) -> Dict[str, Any]:
    return normalize_onboarding(row.onboarding)


def _save_section(db: Session, row: FactoryProfile, key: str, data: Dict[str, Any], status: str) -> Dict[str, Any]:
    if key not in STEP_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown onboarding section '{key}'.")
    state = _state(row)
    state["sections"][key] = {"status": status, "data": data}
    # Advance the step pointer but never move backwards past the saved section.
    idx = STEP_KEYS.index(key) + 1
    state["current_step"] = max(int(state.get("current_step") or 1), min(idx + 1, len(STEP_KEYS)))
    if state["status"] != STATUS_COMPLETE:
        state["status"] = STATUS_IN_PROGRESS
    row.onboarding = state
    db.commit()
    db.refresh(row)
    return state


def _not_available(db: Session, row: FactoryProfile, key: str) -> Dict[str, Any]:
    state = _state(row)
    state["sections"][key] = {"status": SECTION_NOT_AVAILABLE, "data": {}}
    if state["status"] != STATUS_COMPLETE:
        state["status"] = STATUS_IN_PROGRESS
    row.onboarding = state
    db.commit()
    db.refresh(row)
    return state


def _rows_from_body(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    if isinstance(body.get("rows"), list):
        return body["rows"]
    if body.get("csv_text"):
        return parse_csv(str(body["csv_text"]))
    return []


@router.get("/state")
def get_state(db: Session = Depends(get_db)):
    row = _factory(db)
    return {
        "factory": factory_summary(db, row),
        "onboarding": _state(row),
    }


# ---------------------------------------------------------------------------
# Section writers
# ---------------------------------------------------------------------------
@router.put("/company")
def put_company(body: Dict[str, Any], db: Session = Depends(get_db)):
    row = _factory(db)
    data, errors = validate_company(body)
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})
    row.name = data["name"]
    row.industry = data["industry"]
    row.answers = {**(row.answers or {}), **data}
    return {"onboarding": _save_section(db, row, "company", data, SECTION_AVAILABLE)}


@router.put("/production")
def put_production(body: Dict[str, Any], db: Session = Depends(get_db)):
    row = _factory(db)
    data, errors = validate_production(body)
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})
    return {"onboarding": _save_section(db, row, "production", data, SECTION_AVAILABLE)}


@router.put("/thresholds")
def put_thresholds(body: Dict[str, Any], db: Session = Depends(get_db)):
    row = _factory(db)
    data, errors = validate_thresholds(body)
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})
    status = SECTION_DEFAULT if data["mode"] == "default" else SECTION_AVAILABLE
    state = _save_section(db, row, "thresholds", data, status)
    _sync_profile(row, state)
    db.commit()
    return {"onboarding": _state(row)}


@router.post("/thresholds/use-defaults")
def use_default_thresholds(db: Session = Depends(get_db)):
    row = _factory(db)
    data = {"mode": "default", "default": dict(DEFAULT_THRESHOLDS), "by_type": {}}
    state = _save_section(db, row, "thresholds", data, SECTION_DEFAULT)
    _sync_profile(row, state)
    db.commit()
    return {"onboarding": _state(row)}


@router.put("/ai-preferences")
@router.put("/ai_preferences")
def put_ai_preferences(body: Dict[str, Any], db: Session = Depends(get_db)):
    row = _factory(db)
    data, errors = validate_ai_preferences(body)
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})
    return {"onboarding": _save_section(db, row, "ai_preferences", data, SECTION_AVAILABLE)}


@router.post("/ai-preferences/use-defaults")
@router.post("/ai_preferences/use-defaults")
def use_default_ai_preferences(db: Session = Depends(get_db)):
    row = _factory(db)
    return {"onboarding": _save_section(db, row, "ai_preferences", dict(DEFAULT_AI_PREFERENCES), SECTION_DEFAULT)}


# ---------------------------------------------------------------------------
# List sections (employees / machines / orders / maintenance)
# ---------------------------------------------------------------------------
@router.put("/employees")
def put_employees(body: Dict[str, Any], db: Session = Depends(get_db)):
    row = _factory(db)
    if (body.get("mode") or "").lower() == "not_available":
        return {"onboarding": _not_available(db, row, "employees")}
    rows, errors = validate_employee_rows(_rows_from_body(body))
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})
    if not rows:
        raise HTTPException(status_code=422, detail={"errors": ["No employee rows to import."]})
    existing_names = {(e.name or "").strip().lower() for e in db.query(Employee).all()}
    existing_codes = {e.employee_code for e in db.query(Employee).all() if e.employee_code}
    created = skipped = 0
    for r in rows:
        code = r.get("employee_id")
        if (code and code in existing_codes) or r["name"].lower() in existing_names:
            skipped += 1
            continue
        db.add(Employee(
            name=r["name"], role=r["role"], department=r["department"],
            employee_code=code, skills=r["skills"],
            certifications=r["certifications"], shift=r["shift"],
            experience_years=r["experience_years"], status="ACTIVE", availability="AVAILABLE",
        ))
        existing_names.add(r["name"].lower())
        if code:
            existing_codes.add(code)
        created += 1
    db.commit()
    data = {"mode": "available", "count": created, "skipped": skipped, "rows": rows}
    return {"onboarding": _save_section(db, row, "employees", data, SECTION_AVAILABLE), "created": created, "skipped": skipped}


@router.put("/machines")
def put_machines(body: Dict[str, Any], db: Session = Depends(get_db)):
    row = _factory(db)
    if (body.get("mode") or "").lower() == "not_available":
        return {"onboarding": _not_available(db, row, "machines")}
    rows, errors = validate_machine_rows(_rows_from_body(body))
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})
    if not rows:
        raise HTTPException(status_code=422, detail={"errors": ["No machine rows to import."]})
    existing = db.query(Machine).all()
    existing_codes = {m.machine_code for m in existing if m.machine_code}
    existing_names = {(m.name or "").strip().lower() for m in existing}
    created = skipped = 0
    for r in rows:
        if (r["machine_code"] and r["machine_code"] in existing_codes) or r["name"].lower() in existing_names:
            skipped += 1
            continue
        db.add(Machine(
            name=r["name"], machine_type=r["machine_type"], location=r["location"],
            machine_code=r["machine_code"], department=r["department"],
            criticality=r["criticality"], status=r["status"], health_status="GOOD",
        ))
        existing_names.add(r["name"].lower())
        if r["machine_code"]:
            existing_codes.add(r["machine_code"])
        created += 1
    db.commit()
    data = {"mode": "available", "count": created, "skipped": skipped, "rows": rows}
    return {"onboarding": _save_section(db, row, "machines", data, SECTION_AVAILABLE), "created": created, "skipped": skipped}


@router.put("/orders")
def put_orders(body: Dict[str, Any], db: Session = Depends(get_db)):
    row = _factory(db)
    if (body.get("mode") or "").lower() == "not_available":
        return {"onboarding": _not_available(db, row, "orders")}
    rows, errors = validate_order_rows(_rows_from_body(body))
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})
    if not rows:
        raise HTTPException(status_code=422, detail={"errors": ["No order rows to import."]})
    existing_numbers = {(o.order_number or "").strip().lower() for o in db.query(Order).all()}
    created = skipped = 0
    for r in rows:
        if r["order_number"].lower() in existing_numbers:
            skipped += 1
            continue
        dl = datetime.fromisoformat(r["deadline"]) if r.get("deadline") else None
        db.add(Order(
            order_number=r["order_number"], customer_name=r["customer_name"],
            product=r["product"], quantity=r["quantity"], priority=r["priority"],
            deadline=dl, status="PENDING", progress=0.0,
        ))
        existing_numbers.add(r["order_number"].lower())
        created += 1
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail={"errors": ["An order number already exists in another company."]})
    data = {"mode": "available", "count": created, "skipped": skipped, "rows": rows}
    return {"onboarding": _save_section(db, row, "orders", data, SECTION_AVAILABLE), "created": created, "skipped": skipped}


@router.put("/maintenance")
def put_maintenance(body: Dict[str, Any], db: Session = Depends(get_db)):
    row = _factory(db)
    if (body.get("mode") or "").lower() == "not_available":
        return {"onboarding": _not_available(db, row, "maintenance")}
    machines = db.query(Machine).all()
    by_code = {}
    for m in machines:
        code = m.machine_code
        if not code and m.name and len(m.name) >= 5 and m.name.upper().startswith("M-"):
            code = m.name[:5].upper()
        if code:
            by_code[code.upper()] = m
    rows, errors = validate_maintenance_rows(_rows_from_body(body), by_code)
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})
    if not rows:
        raise HTTPException(status_code=422, detail={"errors": ["No maintenance rows to import."]})
    existing_keys = set()
    for m in db.query(Maintenance).all():
        existing_keys.add((str(m.machine_id), (m.issue or "").lower(),
                           m.maintenance_date.date().isoformat() if m.maintenance_date else ""))
    created = skipped = 0
    for r in rows:
        key = (str(r["machine_id"]), r["issue"].lower(), (r["maintenance_date"] or "")[:10])
        if key in existing_keys:
            skipped += 1
            continue
        mdate = datetime.fromisoformat(r["maintenance_date"]) if r.get("maintenance_date") else None
        db.add(Maintenance(
            machine_id=UUID(r["machine_id"]), issue=r["issue"], description=r["description"],
            technician=r["technician"], maintenance_date=mdate,
            resolution=r["resolution"], status=r["status"],
        ))
        existing_keys.add(key)
        created += 1
    db.commit()
    data = {"mode": "available", "count": created, "skipped": skipped, "rows": rows}
    return {"onboarding": _save_section(db, row, "maintenance", data, SECTION_AVAILABLE), "created": created, "skipped": skipped}


# ---------------------------------------------------------------------------
# Review / complete
# ---------------------------------------------------------------------------
def _sync_profile(row: FactoryProfile, state: Dict[str, Any]) -> None:
    """Mirror onboarding data into the legacy ``profile`` JSONB so existing
    AI/threshold/map features keep working without knowing about onboarding."""
    profile = dict(row.profile) if isinstance(row.profile, dict) else {}
    sec = state["sections"]
    company = sec.get("company", {}).get("data") or {}
    production = sec.get("production", {}).get("data") or {}
    machines = sec.get("machines", {}).get("data") or {}
    if company:
        profile["industry"] = company.get("industry") or profile.get("industry")
        profile["description"] = profile.get("description") or ""
    # thresholds always present so resolve_thresholds sees the factory's set
    profile["thresholds"] = profile_thresholds_from_onboarding(state)
    if production.get("shifts"):
        profile["shifts"] = [
            f"{s.get('name')} ({s.get('start_time')}-{s.get('end_time')})" for s in production["shifts"]
        ]
    if isinstance(machines.get("rows"), list):
        profile["machines"] = [
            {"code": m.get("machine_code") or "", "name": m.get("name") or "",
             "machine_type": m.get("machine_type") or "", "location": m.get("location") or "",
             "sensors": ["temperature", "vibration", "current", "rpm"]}
            for m in machines["rows"]
        ]
    profile.setdefault("_source", "preset")
    row.profile = profile


@router.post("/complete")
def complete_onboarding(db: Session = Depends(get_db)):
    row = _factory(db)
    state = _state(row)
    missing = [k for k in REQUIRED_SECTIONS if state["sections"].get(k, {}).get("status") == SECTION_PENDING]
    if missing:
        raise HTTPException(
            status_code=422,
            detail={"errors": [f"Finish required section '{k}' before completing setup." for k in missing]},
        )
    _sync_profile(row, state)
    state["status"] = STATUS_COMPLETE
    state["current_step"] = len(STEP_KEYS)
    row.onboarding = state
    row.status = "APPROVED"
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return {"factory": factory_summary(db, row), "onboarding": state, "setup_complete": True}


@router.get("/status")
def onboarding_status(db: Session = Depends(get_db)):
    row = _factory(db)
    return {
        "factory_id": str(row.id),
        "setup_complete": factory_setup_complete(row),
        "status": row.status,
        "onboarding_status": _state(row).get("status"),
    }
