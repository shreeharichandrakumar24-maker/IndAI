"""Contracts for work plans + dispatch (Phase 7)."""
from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class PlanItem(BaseModel):
    task_name: str
    description: Optional[str] = None
    required_skill: Optional[str] = None
    machine_type: Optional[str] = None
    order_id: Optional[UUID] = None
    priority: Optional[str] = "NORMAL"
    deadline: Optional[datetime] = None

    model_config = ConfigDict(extra="ignore")


class PlanCreate(BaseModel):
    title: str
    description: Optional[str] = None
    items: List[PlanItem] = Field(default_factory=list, max_length=100)


class PlanResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    payload: Optional[dict] = None
    status: str
    created_by: Optional[UUID] = None
    approved_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssignmentResponse(BaseModel):
    id: UUID
    plan_id: UUID
    task_id: Optional[UUID] = None
    employee_id: Optional[UUID] = None
    machine_id: Optional[UUID] = None
    status: str
    notified_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssignmentUpdate(BaseModel):
    status: str  # ACCEPTED | IN_PROGRESS | DONE
    note: Optional[str] = None


class TokenBody(BaseModel):
    token: str
    platform: Optional[str] = "android"


class CandidateWorker(BaseModel):
    id: str
    name: str
    skills: List[str] = Field(default_factory=list)
    open_tasks: int = 0
    shift: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class CandidateMachine(BaseModel):
    id: str
    name: str
    machine_type: Optional[str] = None
    health_status: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class SuggestItem(BaseModel):
    """One AI-ranked pairing. UNASSIGNABLE when nothing fits (with reasons)."""

    assignment_id: str
    employee_id: Optional[str] = None
    machine_id: Optional[str] = None
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    reasons: List[str] = Field(default_factory=list)
    status: str = "SUGGESTED"  # SUGGESTED | UNASSIGNABLE

    model_config = ConfigDict(extra="ignore")


class SuggestResponse(BaseModel):
    source: str = "ai"  # ai | deterministic
    suggestions: List[SuggestItem] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class SuggestResult(BaseModel):
    suggestions: List[SuggestItem] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class PairBody(BaseModel):
    employee_id: Optional[UUID] = None
    machine_id: Optional[UUID] = None
