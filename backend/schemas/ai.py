"""Strict Pydantic contracts for incident AI analysis (Phase E).

The LLM may only output within IncidentAnalysis; unknown ids are dropped
by validation in the endpoint. Deterministic risk is computed by the
backend (context.py), never by the LLM.
"""
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from uuid import UUID


class RootCause(BaseModel):
    summary: str
    contributing_factors: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    model_config = ConfigDict(extra="ignore")


class OrderRiskItem(BaseModel):
    order_id: str
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    reason: str = ""
    estimated_delay_hours: Optional[float] = None

    model_config = ConfigDict(extra="ignore")


class RecommendationItem(BaseModel):
    action_type: Literal["SCHEDULE_MAINTENANCE", "REASSIGN_TASK", "DELAY_TASK", "MONITOR", "ESCALATE"]
    title: str
    detail: str = ""

    model_config = ConfigDict(extra="ignore")


class IncidentAnalysis(BaseModel):
    root_cause: RootCause
    order_risk: List[OrderRiskItem] = Field(default_factory=list)
    recommendations: List[RecommendationItem] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class DecisionBody(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    note: Optional[str] = None


class ProposedAction(BaseModel):
    """One executable proposal. Only these two kinds exist; the frontend
    applies them through the normal endpoints after the user clicks Apply."""

    action_type: Literal["SCHEDULE_MAINTENANCE", "UPDATE_TASK_STATUS"]
    title: str = ""
    detail: str = ""
    machine_id: Optional[str] = None
    task_id: Optional[str] = None
    status: Optional[str] = None
    issue: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class AssistantReply(BaseModel):
    answer: str
    used_facts: List[str] = Field(default_factory=list)
    proposed_actions: List[ProposedAction] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class ChatBody(BaseModel):
    message: str
    history: List[dict] = Field(default_factory=list, max_length=20)


class RootCauseScope(BaseModel):
    machine_id: Optional[UUID] = None
    order_id: Optional[UUID] = None


class EvidenceItem(BaseModel):
    system: str  # telemetry | tasks | orders | maintenance | memory | incidents
    fact: str = ""

    model_config = ConfigDict(extra="ignore")


class RelatedIds(BaseModel):
    machines: List[str] = Field(default_factory=list)
    orders: List[str] = Field(default_factory=list)
    tasks: List[str] = Field(default_factory=list)
    incidents: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class RootCauseAnalysis(BaseModel):
    primary_cause: str
    evidence: List[EvidenceItem] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    related_ids: RelatedIds = Field(default_factory=RelatedIds)

    model_config = ConfigDict(extra="ignore")


class DelayEstimate(BaseModel):
    order_id: str
    estimated_delay_hours: Optional[float] = None
    reason: str = ""

    model_config = ConfigDict(extra="ignore")


class DelayEstimates(BaseModel):
    estimates: List[DelayEstimate] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class SimulateBody(BaseModel):
    scenario_type: Literal["DELAY_ORDER", "RESOLVE_INCIDENT", "REASSIGN_TASK"]
    order_id: Optional[UUID] = None
    incident_id: Optional[UUID] = None
    task_id: Optional[UUID] = None
    employee_id: Optional[UUID] = None
    machine_id: Optional[UUID] = None
    days: Optional[float] = None


class AffectedOrder(BaseModel):
    order_id: str
    order_number: Optional[str] = None
    old_risk: str = ""
    new_risk: str = ""
    old_reason: str = ""
    new_reason: str = ""
    new_deadline: Optional[str] = None
    delta_hours: Optional[float] = None

    model_config = ConfigDict(extra="ignore")


class SimulationResult(BaseModel):
    scenario: str
    assumptions: List[str] = Field(default_factory=list)
    affected_orders: List[AffectedOrder] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    feasibility: Optional[dict] = None
    narrative: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class SplitTaskProposal(BaseModel):
    name: str
    description: Optional[str] = None
    required_skill: Optional[str] = None
    priority: Optional[str] = "NORMAL"
    machine_id: Optional[str] = None
    employee_id: Optional[str] = None
    suggested_deadline: Optional[str] = None
    rationale: str = ""

    model_config = ConfigDict(extra="ignore")


class SplitProposal(BaseModel):
    summary: str = ""
    proposed_tasks: List[SplitTaskProposal] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class SmartSplitBody(BaseModel):
    order_id: UUID


class AssistantMessage(BaseModel):
    role: str = "user"
    content: str = ""

    model_config = ConfigDict(extra="ignore")


class AssistantChatBody(BaseModel):
    messages: List[AssistantMessage] = Field(default_factory=list, max_length=10)


class VoiceBody(BaseModel):
    messages: List[AssistantMessage] = Field(default_factory=list, max_length=6)

class AssistantAction(BaseModel):
    action_type: Literal["SCHEDULE_MAINTENANCE", "REASSIGN_TASK", "DELAY_TASK", "DRAFT_ASSIGNMENT"]
    title: str = ""
    detail: str = ""
    params: dict = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class AssistantTurn(BaseModel):
    """One bounded model turn: either a tool call or the final answer."""

    type: Literal["tool_call", "final"]
    tool: Optional[str] = None
    args: Optional[dict] = None
    reply: Optional[str] = None
    proposed_actions: List[AssistantAction] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class RecommendationResponse(BaseModel):
    id: UUID
    recommendation_type: str
    entity_type: str
    entity_id: UUID
    recommendation: str
    reason: Optional[str] = None
    confidence: Optional[float] = None
    status: str
    params: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MemoryResponse(BaseModel):
    id: UUID
    title: str
    event_type: Optional[str] = None
    description: Optional[str] = None
    machine_id: Optional[UUID] = None
    order_id: Optional[UUID] = None
    task_id: Optional[UUID] = None
    resolution_action: Optional[str] = None
    # Column is named "metadata" in Postgres, mapped as metadata_ in Python
    # (metadata is reserved on SQLAlchemy Base). serialization_alias keeps the
    # API key as "metadata" without breaking from_attributes validation.
    metadata_: Optional[dict] = Field(default=None, serialization_alias="metadata")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
