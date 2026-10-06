from pydantic import BaseModel, ConfigDict
from typing import List, Optional


class WhatIfRequest(BaseModel):
    scenario: str


class WhatIfScenario(BaseModel):
    type: str
    entity_id: str
    entity_name: str
    duration_hours: float
    reason: Optional[str] = None


class WhatIfImpact(BaseModel):
    affected_tasks: int
    affected_orders: int
    affected_production_runs: int
    estimated_delay_hours: float
    estimated_units_at_risk: int = 0


class WhatIfTaskItem(BaseModel):
    id: str
    name: str
    order_id: Optional[str] = None
    current_progress: float = 0.0
    status: Optional[str] = None


class WhatIfAlternative(BaseModel):
    type: str
    id: str
    name: str
    reason: str


class WhatIfResult(BaseModel):
    scenario: WhatIfScenario
    summary: str
    impact: WhatIfImpact
    affected_tasks: List[WhatIfTaskItem] = []
    affected_order_ids: List[str] = []
    alternatives: List[WhatIfAlternative] = []
    recommendation: str
    assumptions: List[str] = []
    narrative: Optional[str] = None
    simulation_only: bool = True

    model_config = ConfigDict(from_attributes=True)
