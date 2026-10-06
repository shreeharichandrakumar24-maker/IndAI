from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from backend.db.database import get_db

from backend.models.models import Incident
from backend.schemas.incident import IncidentCreate, IncidentUpdate, IncidentResponse

router = APIRouter()

@router.post("", response_model=IncidentResponse)
def create_incident(incident: IncidentCreate, db: Session = Depends(get_db)):
    db_inc = Incident(**incident.model_dump())
    db.add(db_inc)
    db.commit()
    db.refresh(db_inc)
    return db_inc

def _enrich_incident_resp(inc: Incident, db: Session) -> IncidentResponse:
    item = IncidentResponse.model_validate(inc)
    if inc.employee:
        item.employee_name = inc.employee.name
        item.employee_role = inc.employee.role
    if inc.machine:
        item.machine_name = inc.machine.name
        try:
            from backend.models.models import FactoryProfile
            if inc.machine.factory_id:
                f = db.query(FactoryProfile).filter(FactoryProfile.id == inc.machine.factory_id).first()
                item.company_name = (f.name or f.industry) if f else "CNC / Mechanical"
            else:
                default_f = db.query(FactoryProfile).filter(FactoryProfile.is_default == True).first()
                item.company_name = (default_f.name or default_f.industry) if default_f else "CNC / Mechanical"
        except Exception:
            item.company_name = "CNC / Mechanical"
    return item

@router.get("", response_model=List[IncidentResponse])
def get_incidents(
    status: Optional[str] = None, 
    severity: Optional[str] = None,
    machine_id: Optional[UUID] = None,
    task_id: Optional[UUID] = None,
    employee_id: Optional[UUID] = None,
    order_id: Optional[UUID] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Incident)
    if status: query = query.filter(Incident.status == status)
    if severity: query = query.filter(Incident.severity == severity)
    if machine_id: query = query.filter(Incident.machine_id == machine_id)
    if task_id: query = query.filter(Incident.task_id == task_id)
    if employee_id: query = query.filter(Incident.employee_id == employee_id)
    if order_id: query = query.filter(Incident.order_id == order_id)
    rows = query.all()
    return [_enrich_incident_resp(r, db) for r in rows]

@router.get("/{incident_id}", response_model=IncidentResponse)
def get_incident(incident_id: UUID, db: Session = Depends(get_db)):
    db_inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not db_inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    return _enrich_incident_resp(db_inc, db)

@router.put("/{incident_id}", response_model=IncidentResponse)
def update_incident(incident_id: UUID, incident: IncidentUpdate, db: Session = Depends(get_db)):
    db_inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not db_inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    update_data = incident.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_inc, key, value)
    db.commit()
    db.refresh(db_inc)
    return db_inc

@router.delete("/{incident_id}")
def delete_incident(incident_id: UUID, db: Session = Depends(get_db)):
    db_inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not db_inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    db.delete(db_inc)
    db.commit()
    return {"message": "Incident deleted"}
