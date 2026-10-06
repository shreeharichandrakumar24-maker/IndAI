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

@router.get("/{machine_id}/alert")
def get_machine_alert(machine_id: UUID, db: Session = Depends(get_db)):
    """Detailed alert status, breach parameters, and assigned maintenance service man for a machine."""
    db_machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if not db_machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    
    from backend.services.abnormality import latest_telemetry, evaluate_telemetry, resolve_thresholds, open_incident_for_machine, find_service_technician
    from backend.models.models import FactoryProfile, Employee, Maintenance
    
    thresholds = resolve_thresholds(db_machine.machine_type, db, db_machine.factory_id)
    tel = latest_telemetry(db, machine_id)
    eval_res = evaluate_telemetry(tel, thresholds)
    incident = open_incident_for_machine(db, machine_id)
    
    company_name = "CNC / Mechanical"
    if db_machine.factory_id:
        f = db.query(FactoryProfile).filter(FactoryProfile.id == db_machine.factory_id).first()
        if f: company_name = f.name or f.industry
    else:
        default_f = db.query(FactoryProfile).filter(FactoryProfile.is_default == True).first()
        if default_f: company_name = default_f.name or default_f.industry
    
    service_man = None
    if incident and incident.employee_id:
        emp = db.query(Employee).filter(Employee.id == incident.employee_id).first()
        if emp:
            service_man = {"id": str(emp.id), "name": emp.name, "role": emp.role, "availability": emp.availability}
    
    if not service_man:
        maint = db.query(Maintenance).filter(Maintenance.machine_id == machine_id, Maintenance.status == "PENDING").first()
        if maint and maint.technician:
            service_man = {"id": None, "name": maint.technician.split(" (")[0], "role": maint.technician, "availability": "ASSIGNED"}
    
    if not service_man:
        tech = find_service_technician(db, db_machine, eval_res["breaches"])
        if tech:
            service_man = {"id": str(tech.id), "name": tech.name, "role": tech.role, "availability": tech.availability}
            
    return {
        "machine_id": str(machine_id),
        "machine_name": db_machine.name,
        "machine_code": db_machine.machine_code or db_machine.name.split(" ")[0],
        "company_name": company_name,
        "health_status": db_machine.health_status,
        "status": db_machine.status,
        "is_abnormal": eval_res["abnormal"],
        "severity": eval_res["severity"] or (incident.severity if incident else "NORMAL"),
        "breaches": eval_res["breaches"],
        "telemetry": {
            "temperature": tel.temperature if tel else None,
            "vibration": tel.vibration if tel else None,
            "current": tel.current if tel else None,
            "rpm": tel.rpm if tel else None,
            "timestamp": tel.timestamp.isoformat() if tel and tel.timestamp else None,
        } if tel else None,
        "thresholds": thresholds,
        "open_incident": {
            "id": str(incident.id),
            "severity": incident.severity,
            "description": incident.description,
            "created_at": incident.created_at.isoformat() if incident.created_at else None,
        } if incident else None,
        "service_man": service_man,
    }

@router.delete("/{machine_id}")
def delete_machine(machine_id: UUID, db: Session = Depends(get_db)):
    db_machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if not db_machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    db.delete(db_machine)
    db.commit()
    return {"message": "Machine deleted"}
