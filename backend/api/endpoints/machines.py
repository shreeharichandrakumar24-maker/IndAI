from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from backend.db.database import get_db

from backend.models.models import Machine, MachineTelemetry
from backend.schemas.machine import MachineCreate, MachineUpdate, MachineResponse
from backend.schemas.telemetry import TelemetryResponse

router = APIRouter()

@router.post("", response_model=MachineResponse)
def create_machine(machine: MachineCreate, db: Session = Depends(get_db)):
    db_machine = Machine(**machine.model_dump())
    db.add(db_machine)
    db.commit()
    db.refresh(db_machine)
    return db_machine

@router.get("", response_model=List[MachineResponse])
def get_machines(status: Optional[str] = None, health_status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Machine)
    if status:
        query = query.filter(Machine.status == status)
    if health_status:
        query = query.filter(Machine.health_status == health_status)
    rows = query.all()
    if not rows:
        return []
    from backend.models.models import FactoryProfile
    factories = {f.id: (f.name or f.industry or "Default Factory") for f in db.query(FactoryProfile).all()}
    default_f = db.query(FactoryProfile).filter(FactoryProfile.is_default == True).first()
    default_name = (default_f.name or default_f.industry) if default_f else "Default Factory"

    result = []
    for m in rows:
        item = MachineResponse.model_validate(m)
        item.company_name = factories.get(m.factory_id) or default_name
        result.append(item)
    return result

@router.get("/{machine_id}", response_model=MachineResponse)
def get_machine(machine_id: UUID, db: Session = Depends(get_db)):
    db_machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if not db_machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    item = MachineResponse.model_validate(db_machine)
    from backend.models.models import FactoryProfile
    if db_machine.factory_id:
        f = db.query(FactoryProfile).filter(FactoryProfile.id == db_machine.factory_id).first()
        item.company_name = (f.name or f.industry) if f else "Default Factory"
    else:
        default_f = db.query(FactoryProfile).filter(FactoryProfile.is_default == True).first()
        item.company_name = (default_f.name or default_f.industry) if default_f else "Default Factory"
    return item

@router.get("/{machine_id}/telemetry", response_model=List[TelemetryResponse])
def get_machine_telemetry(machine_id: UUID, limit: int = 50, db: Session = Depends(get_db)):
    db_machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if not db_machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    telemetry = db.query(MachineTelemetry).filter(MachineTelemetry.machine_id == machine_id).order_by(MachineTelemetry.timestamp.desc()).limit(limit).all()
    return telemetry

@router.put("/{machine_id}", response_model=MachineResponse)
def update_machine(machine_id: UUID, machine: MachineUpdate, db: Session = Depends(get_db)):
    db_machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if not db_machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    update_data = machine.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_machine, key, value)
    db.commit()
    db.refresh(db_machine)
    return db_machine

@router.delete("/{machine_id}")
def delete_machine(machine_id: UUID, db: Session = Depends(get_db)):
    db_machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if not db_machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    db.delete(db_machine)
    db.commit()
    return {"message": "Machine deleted"}
