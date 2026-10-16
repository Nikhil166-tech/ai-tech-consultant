from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class CapabilityStatus(str, Enum):
    NATIVE = "NATIVE"
    PARTIAL = "PARTIAL"
    CUSTOM = "CUSTOM"
    UNKNOWN = "UNKNOWN"


class RequirementLifecycleStatus(str, Enum):
    NEW = "NEW"
    UNCHANGED = "UNCHANGED"
    CHANGED = "CHANGED"
    REMOVED = "REMOVED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class Task1Citation(BaseModel):
    url: str
    title: str
    category: str = ""
    folder: str = ""
    section_heading: str
    snippet: str = ""
    source_type: str = "OFFICIAL_DOC"


class Task1AskResponse(BaseModel):
    answer: str
    citations: list[Task1Citation] = Field(default_factory=list)
    evidence_score: float = 0.0
    evidence_status: str = "NONE"
    is_known: bool = False
    needs_human_review: bool = True
    expert_task_id: str | None = None
    visual_references: list[dict[str, Any]] = Field(default_factory=list)


class EstimateRange(BaseModel):
    optimistic_hours: float = 0.0
    most_likely_hours: float = 0.0
    pessimistic_hours: float = 0.0
    expected_hours: float = 0.0
    complexity_level: str = "LOW"  # NONE | LOW | MEDIUM | HIGH
    assumptions: list[str] = Field(default_factory=list)
    technical_risks: list[str] = Field(default_factory=list)

    @classmethod
    def calculate(
        cls,
        optimistic: float,
        most_likely: float,
        pessimistic: float,
        complexity: str = "LOW",
        assumptions: list[str] | None = None,
        risks: list[str] | None = None,
    ) -> "EstimateRange":
        # Three-point PERT calculation: (O + 4M + P) / 6
        expected = round((optimistic + (4.0 * most_likely) + pessimistic) / 6.0, 1)
        return cls(
            optimistic_hours=round(optimistic, 1),
            most_likely_hours=round(most_likely, 1),
            pessimistic_hours=round(pessimistic, 1),
            expected_hours=expected,
            complexity_level=complexity,
            assumptions=assumptions or [],
            technical_risks=risks or [],
        )


class RequirementItem(BaseModel):
    id: str  # e.g., "REQ-01"
    title: str
    description: str
    category: str = "GENERAL"
    capability_status: CapabilityStatus = CapabilityStatus.UNKNOWN
    citations: list[Task1Citation] = Field(default_factory=list)
    native_alternative_notes: str | None = None
    estimate: EstimateRange | None = None
    status: RequirementLifecycleStatus = RequirementLifecycleStatus.NEW
    change_reason: str | None = None


class ScopeChangeSet(BaseModel):
    new_requirements: list[RequirementItem] = Field(default_factory=list)
    changed_requirements: list[RequirementItem] = Field(default_factory=list)
    unchanged_requirements: list[RequirementItem] = Field(default_factory=list)
    removed_requirements: list[RequirementItem] = Field(default_factory=list)
    out_of_scope_requirements: list[RequirementItem] = Field(default_factory=list)
    diff_summary: str = ""


class ProjectScope(BaseModel):
    project_id: str
    version: int = 1
    meeting_count: int = 1
    client_goal: str
    requirements: list[RequirementItem] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)

    # Confirmed custom development hours (CUSTOM and PARTIAL items only)
    custom_hours_range: tuple[float, float] = (0.0, 0.0)
    expected_custom_hours: float = 0.0

    # Feasibility / discovery spike hours (UNKNOWN items only, strictly separate)
    discovery_hours_range: tuple[float, float] = (0.0, 0.0)
    expected_discovery_hours: float = 0.0

    # Backwards-compatible aliases for custom dev total
    total_custom_hours_range: tuple[float, float] = (0.0, 0.0)
    expected_total_hours: float = 0.0

    source_citations: list[Task1Citation] = Field(default_factory=list)
    proposal_markdown: str | None = None
    client_ready: bool = False  # Strictly defaults to False! Model cannot self-approve.
    approved_by: str | None = None
    approved_at: datetime | None = None

    # Version history & decision context
    version_history: list[dict[str, Any]] = Field(default_factory=list)
    change_history: list[ScopeChangeSet] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))