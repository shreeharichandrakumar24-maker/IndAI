from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

class ProductionRunBase(BaseModel):
    order_id: Optional[UUID] = None
    task_id: Optional[UUID] = None
    machine_id: Optional[UUID] = None
    quantity_target: Optional[int] = 0
    quantity_completed: Optional[int] = 0
    status: Optional[str] = "PLANNED"
    start_time: Optional[datetime] = None
    estimated_completion: Optional[datetime] = None

class ProductionRunCreate(ProductionRunBase):
    pass

class ProductionRunUpdate(BaseModel):
    order_id: Optional[UUID] = None
    task_id: Optional[UUID] = None
    machine_id: Optional[UUID] = None
    quantity_target: Optional[int] = None
    quantity_completed: Optional[int] = None
    status: Optional[str] = None
    start_time: Optional[datetime] = None
    estimated_completion: Optional[datetime] = None

class ProductionRunResponse(ProductionRunBase):
    id: UUID
    factory_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
