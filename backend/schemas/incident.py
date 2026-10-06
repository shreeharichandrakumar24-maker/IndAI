from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

class IncidentBase(BaseModel):
    machine_id: Optional[UUID] = None
    task_id: Optional[UUID] = None
    employee_id: Optional[UUID] = None
    order_id: Optional[UUID] = None
    incident_type: str
    severity: Optional[str] = "MEDIUM"
    description: Optional[str] = None
    status: Optional[str] = "OPEN"

class IncidentCreate(IncidentBase):
    pass

class IncidentUpdate(BaseModel):
    machine_id: Optional[UUID] = None
    task_id: Optional[UUID] = None
    employee_id: Optional[UUID] = None
    order_id: Optional[UUID] = None
    incident_type: Optional[str] = None
    severity: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

class IncidentResponse(IncidentBase):
    id: UUID
    employee_name: Optional[str] = None
    employee_role: Optional[str] = None
    machine_name: Optional[str] = None
    company_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
