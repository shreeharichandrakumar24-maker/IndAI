from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

class TaskBase(BaseModel):
    name: str
    description: Optional[str] = None
    required_skill: Optional[str] = None
    priority: Optional[str] = "NORMAL"
    status: Optional[str] = "PENDING"
    employee_id: Optional[UUID] = None
    machine_id: Optional[UUID] = None
    order_id: Optional[UUID] = None
    start_time: Optional[datetime] = None
    deadline: Optional[datetime] = None
    progress: Optional[float] = 0.0

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    required_skill: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    employee_id: Optional[UUID] = None
    machine_id: Optional[UUID] = None
    order_id: Optional[UUID] = None
    start_time: Optional[datetime] = None
    deadline: Optional[datetime] = None
    progress: Optional[float] = None

class TaskResponse(TaskBase):
    id: UUID
    factory_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
