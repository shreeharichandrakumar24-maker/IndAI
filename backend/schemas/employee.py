from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from uuid import UUID

class EmployeeBase(BaseModel):
    name: str
    role: str
    skills: Optional[Any] = None
    certifications: Optional[Any] = None
    shift: Optional[str] = None
    status: Optional[str] = "ACTIVE"
    availability: Optional[str] = "AVAILABLE"
    department: Optional[str] = None
    experience_years: Optional[int] = None
    employee_code: Optional[str] = None
    factory_id: Optional[UUID] = None

class EmployeeCreate(EmployeeBase):
    pass

class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    skills: Optional[Any] = None
    certifications: Optional[Any] = None
    shift: Optional[str] = None
    status: Optional[str] = None
    availability: Optional[str] = None
    department: Optional[str] = None
    experience_years: Optional[int] = None
    employee_code: Optional[str] = None
    factory_id: Optional[UUID] = None

class EmployeeResponse(EmployeeBase):
    id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)
