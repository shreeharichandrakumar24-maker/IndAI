"""Pydantic validation for the factory profile JSON (Phase A4).

The LLM is only allowed to output within this schema; unknown
sensors/fields are rejected/dropped by validation.
"""
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


ALLOWED_SENSORS = {"temperature", "vibration", "current", "rpm"}


class Terminology(BaseModel):
    machine: str = "machine"
    order: str = "order"
    task: str = "task"


class ProfileMachine(BaseModel):
    code: str
    name: str
    machine_type: str = "CNC"
    location: Optional[str] = None
    sensors: List[str] = Field(default_factory=lambda: ["temperature", "vibration", "current", "rpm"])

    model_config = ConfigDict(extra="ignore")


class ThresholdSet(BaseModel):
    temp_max: float = 85.0
    vibration_max: float = 5.0
    current_max: float = 10.0
    rpm_min: float = 1300.0

    model_config = ConfigDict(extra="ignore")


class TaskTemplate(BaseModel):
    name: str
    description: Optional[str] = None
    required_skill: Optional[str] = None
    machine_type: Optional[str] = None
    typical_order: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class LayoutZone(BaseModel):
    id: str
    name: str = ""
    x: float = 0
    y: float = 0
    w: float = 100
    h: float = 100

    model_config = ConfigDict(extra="ignore")


class LayoutMachine(BaseModel):
    x: float = 0
    y: float = 0
    zone_id: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class FactoryLayout(BaseModel):
    """Optional floor-plan geometry. Absent in old profiles (still valid)."""

    width: float = 1000
    height: float = 600
    zones: List[LayoutZone] = Field(default_factory=list)
    machines: Dict[str, LayoutMachine] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class FactoryProfileData(BaseModel):
    """The validated profile JSON stored in factory_profile.profile."""

    industry: str = "CNC / Mechanical"
    description: Optional[str] = None
    terminology: Terminology = Field(default_factory=Terminology)
    machines: List[ProfileMachine] = Field(default_factory=list)
    thresholds: Dict[str, ThresholdSet] = Field(default_factory=dict)
    task_templates: List[TaskTemplate] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    shifts: List[str] = Field(default_factory=list)
    main_problems: List[str] = Field(default_factory=list)
    layout: Optional[FactoryLayout] = None

    model_config = ConfigDict(extra="ignore")

    def sanitized(self) -> "FactoryProfileData":
        """Drop unknown sensors (keep only temperature|vibration|current|rpm)."""
        for m in self.machines:
            m.sensors = [s for s in (m.sensors or []) if s in ALLOWED_SENSORS] or ["temperature"]
        if self.layout is not None:
            try:
                self.layout = FactoryLayout.model_validate(self.layout)
            except Exception:
                self.layout = None
        return self


class ProfileAnswers(BaseModel):
    """Onboarding wizard answers (free text + selections)."""

    industry: Optional[str] = None
    products: Optional[str] = None
    machine_types: List[str] = Field(default_factory=list)
    machine_types_other: Optional[str] = None
    shifts_count: Optional[str] = None
    workforce: Optional[str] = None
    skills_text: Optional[str] = None
    main_problems: List[str] = Field(default_factory=list)
    has_files: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class GenerateRequest(BaseModel):
    answers: ProfileAnswers = Field(default_factory=ProfileAnswers)


class FactoryProfileResponse(BaseModel):
    id: str
    industry: Optional[str] = None
    status: str = "DRAFT"
    answers: Optional[dict] = None
    profile: Optional[dict] = None
    source: Optional[str] = None  # "ai" | "preset"
    seed: Optional[dict] = None  # approve-only: {created, skipped}

    model_config = ConfigDict(from_attributes=False)
