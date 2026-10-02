from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from backend.db.database import get_db

from datetime import datetime
from backend.models.models import MachineTelemetry
from backend.schemas.telemetry import TelemetryCreate, TelemetryResponse

router = APIRouter()

@router.post("", response_model=TelemetryResponse)
def create_telemetry(telemetry: TelemetryCreate, db: Session = Depends(get_db)):
    # if timestamp not provided, it will use DB default (now)
    db_tel = MachineTelemetry(**telemetry.model_dump())
    db.add(db_tel)
    db.commit()
    db.refresh(db_tel)
    # Live detection (Phase D): ingestion must never fail because detection
    # failed. Dedup rule (never duplicate an OPEN incident) lives in
    # detect_and_create_incident. Historical/bulk imports use the import
    # endpoint, which never calls this path... note: this endpoint IS the
    # simulator path, so detection runs here by design.
    try:
        from backend.services.abnormality import detect_and_create_incident
        detect_and_create_incident(db, db_tel.machine_id)
    except Exception:
        pass
    return db_tel

@router.get("/{machine_id}", response_model=List[TelemetryResponse])
def get_telemetry(
    machine_id: UUID,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db)
):
    query = db.query(MachineTelemetry).filter(MachineTelemetry.machine_id == machine_id)
    if start_time:
        query = query.filter(MachineTelemetry.timestamp >= start_time)
    if end_time:
        query = query.filter(MachineTelemetry.timestamp <= end_time)
    
    # newest records first
    query = query.order_by(MachineTelemetry.timestamp.desc()).limit(limit)
    return query.all()

@router.get("/latest/{machine_id}", response_model=TelemetryResponse)
def get_latest_telemetry(machine_id: UUID, db: Session = Depends(get_db)):
    db_tel = db.query(MachineTelemetry).filter(MachineTelemetry.machine_id == machine_id).order_by(MachineTelemetry.timestamp.desc()).first()
    if not db_tel:
        raise HTTPException(status_code=404, detail="No telemetry found for this machine")
    return db_tel

@router.post("/{machine_id}/check")
def check_machine_telemetry(machine_id: UUID, db: Session = Depends(get_db)):
    """Run abnormality detection on the latest telemetry for one machine.

    Creates an OPEN incident only when the machine is abnormal and has no
    OPEN incident yet. Never duplicates. Path has two segments so it cannot
    collide with GET /{machine_id}."""
    from backend.services.abnormality import detect_and_create_incident
    result = detect_and_create_incident(db, machine_id)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail="Machine not found")
    return result

@router.post("/check-all")
def check_all_machines(db: Session = Depends(get_db)):
    """Run detection over the latest telemetry of every machine.

    Creates OPEN incidents only where needed; machines with an existing
    OPEN incident are reported, never duplicated."""
    from backend.models.models import Machine
    from backend.services.abnormality import detect_and_create_incident
    machines = db.query(Machine).all()
    results = [detect_and_create_incident(db, m.id) for m in machines]
    created = sum(1 for r in results if r.get("incident_created"))
    abnormal = sum(1 for r in results if r.get("abnormal"))
    return {
        "checked": len(results),
        "abnormal": abnormal,
        "incidents_created": created,
        "results": results,
    }

@router.get("/{machine_id}/health-check")
def health_check_machine(machine_id: UUID, db: Session = Depends(get_db)):
    """Recovery check: is the machine's latest telemetry currently normal?

    Read-only. Never resolves incidents; the admin workflow does that
    explicitly after maintenance completion."""
    from backend.services.abnormality import health_of_machine
    result = health_of_machine(db, machine_id)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail="Machine not found")
    return result
