from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

class TelemetryBase(BaseModel):
    machine_id: UUID
    temperature: Optional[float] = None
    vibration: Optional[float] = None
    current: Optional[float] = None
    rpm: Optional[float] = None
    machine_status: Optional[str] = None
    timestamp: Optional[datetime] = None

class TelemetryCreate(TelemetryBase):
    pass

class TelemetryResponse(TelemetryBase):
    id: UUID
    is_abnormal: Optional[bool] = False
    alert: Optional[Dict[str, Any]] = None
    service_man: Optional[Dict[str, Any]] = None
    model_config = ConfigDict(from_attributes=True)
