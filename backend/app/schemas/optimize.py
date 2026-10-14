import re
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain import (
    IDENTIFIER_PATTERN,
    PLAYSTYLE_IDS,
    BadgeTier,
    Importance,
    PoolKind,
    Position,
    SearchMode,
)
from app.schemas.common import BodyInput, Rating

_IDENTIFIER = re.compile(IDENTIFIER_PATTERN)


def _unique(values: list[str], message: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(message)


class AttributeTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(pattern=IDENTIFIER_PATTERN)
    target: Rating
    importance: Importance


class CapBreakerPoolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(pattern=IDENTIFIER_PATTERN)
    kind: PoolKind
    category: str | None = Field(default=None, pattern=IDENTIFIER_PATTERN)
    # API limit, not a verified Cap Breaker inventory.
    available: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def category_matches_kind(self) -> Self:
        if self.kind is PoolKind.specialization and self.category is None:
            raise ValueError("A specialization pool needs a category.")
        if self.kind is PoolKind.unrestricted and self.category is not None:
            raise ValueError("An unrestricted pool cannot declare a category.")
        return self


class MinimumAllocation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    attribute_id: str = Field(pattern=IDENTIFIER_PATTERN)
    count: int = Field(ge=0, le=100)


class CapBreakerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pools: list[CapBreakerPoolInput] = Field(default_factory=list, max_length=12)
    reserved_total: int = Field(default=0, ge=0, le=100)
    forbidden_attribute_ids: list[str] = Field(default_factory=list, max_length=64)
    minimum_allocations: list[MinimumAllocation] = Field(default_factory=list, max_length=64)

    @field_validator("forbidden_attribute_ids")
    @classmethod
    def identifier_list(cls, values: list[str]) -> list[str]:
        for value in values:
            if _IDENTIFIER.fullmatch(value) is None:
                raise ValueError("Attribute ids must be lowercase identifiers.")
        return values

    @model_validator(mode="after")
    def consistent_budget(self) -> Self:
        _unique([pool.id for pool in self.pools], "Cap Breaker pool ids must be unique.")
        _unique(
            self.forbidden_attribute_ids,
            "Forbidden attribute ids must be unique.",
        )
        _unique(
            [item.attribute_id for item in self.minimum_allocations],
            "Minimum allocations must use each attribute once.",
        )
        available = sum(pool.available for pool in self.pools)
        if self.reserved_total > available:
            raise ValueError("Reserved Cap Breakers cannot exceed the total available.")
        # Totals only. Category legality is a verified game rule and is not applied here.
        spendable = available - self.reserved_total
        requested = sum(item.count for item in self.minimum_allocations)
        if requested > spendable:
            raise ValueError("Minimum Cap Breaker allocations exceed the spendable total.")
        return self


class BadgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(pattern=IDENTIFIER_PATTERN)
    minimum_tier: BadgeTier
    importance: Importance


class UnlockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(pattern=IDENTIFIER_PATTERN)
    importance: Importance


class AttributeRating(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=IDENTIFIER_PATTERN)
    rating: Rating


class BuildMeasurements(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: Position
    height_in: int = Field(ge=1, le=150)
    weight_lb: int = Field(ge=1, le=1000)
    wingspan_in: int = Field(ge=1, le=150)


class CapBreakerAllocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pool_id: str = Field(pattern=IDENTIFIER_PATTERN)
    attribute_id: str = Field(pattern=IDENTIFIER_PATTERN)
    applications: int = Field(ge=0, le=100)
    rating_gain: Rating


class EligibleBadge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=IDENTIFIER_PATTERN)
    highest_tier: BadgeTier


class EligibleUnlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=IDENTIFIER_PATTERN)


class ScoreComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=IDENTIFIER_PATTERN)
    weight: float
    value: float
    note: str = Field(default="", max_length=300)


class ScoreBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scoring_version: str
    components: list[ScoreComponent] = Field(default_factory=list, max_length=32)


class DeviationNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attribute_id: str = Field(pattern=IDENTIFIER_PATTERN)
    requested: Rating
    achieved: Rating
    message: str = Field(min_length=1, max_length=300)


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    build_id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    rank: int = Field(ge=1, le=8)
    score: float = Field(ge=0, le=100)
    body: BuildMeasurements
    base_attributes: list[AttributeRating] = Field(max_length=64)
    final_attributes: list[AttributeRating] = Field(max_length=64)
    cap_breaker_allocations: list[CapBreakerAllocation] = Field(max_length=200)
    eligible_badges: list[EligibleBadge] = Field(max_length=200)
    eligible_animations: list[EligibleUnlock] = Field(max_length=200)
    eligible_takeovers: list[EligibleUnlock] = Field(max_length=50)
    score_breakdown: ScoreBreakdown
    deviations: list[DeviationNote] = Field(max_length=64)
    verification: Literal["verified"]


class RefineReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: BuildMeasurements
    base_attributes: list[AttributeRating] = Field(min_length=1, max_length=64)
    cap_breaker_allocations: list[CapBreakerAllocation] = Field(
        default_factory=list,
        max_length=200,
    )


class OptimizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    mode: SearchMode = SearchMode.generate
    body: BodyInput = Field(default_factory=BodyInput)
    attribute_targets: list[AttributeTarget] = Field(min_length=1, max_length=64)
    cap_breakers: CapBreakerInput = Field(default_factory=CapBreakerInput)
    badges: list[BadgeRequest] = Field(default_factory=list, max_length=200)
    animations: list[UnlockRequest] = Field(default_factory=list, max_length=200)
    takeovers: list[UnlockRequest] = Field(default_factory=list, max_length=50)
    playstyle: str = "automatic"
    reference: RefineReference | None = None

    @field_validator("playstyle")
    @classmethod
    def known_playstyle(cls, value: str) -> str:
        if value not in PLAYSTYLE_IDS:
            raise ValueError("Unknown playstyle.")
        return value

    @model_validator(mode="after")
    def consistent_request(self) -> Self:
        _unique([item.id for item in self.attribute_targets], "Attribute targets must be unique.")
        _unique([item.id for item in self.badges], "Badge requests must be unique.")
        _unique([item.id for item in self.animations], "Animation requests must be unique.")
        _unique([item.id for item in self.takeovers], "Takeover requests must be unique.")
        if self.mode is SearchMode.refine and self.reference is None:
            raise ValueError("Refine mode needs a reference build.")
        if self.mode is SearchMode.generate and self.reference is not None:
            raise ValueError("Generate mode cannot include a reference build.")
        return self


class CoverageReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supported: bool
    notes: list[str]
    missing_mechanics: list[str]


class CacheInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hit: bool


class RecommendationSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top: list[Recommendation] = Field(default_factory=list, max_length=5)
    alternatives: list[Recommendation] = Field(default_factory=list, max_length=3)


class UnmetRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    requested: str
    achieved: str
    message: str


class RequirementConflict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    message: str


class OptimizeResponseBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    ruleset_id: str
    scoring_version: str
    optimizer_version: str
    elapsed_ms: int = Field(ge=0)
    coverage: CoverageReport
    warnings: list[str]
    cache: CacheInfo
    recommendations: RecommendationSet = Field(default_factory=RecommendationSet)
    unmet_requirements: list[UnmetRequirement] = Field(default_factory=list)


class FeasibleOptimizeResponse(OptimizeResponseBase):
    status: Literal["complete_proven", "partial_feasible"]
    optimality_proven: bool


class InconclusiveOptimizeResponse(OptimizeResponseBase):
    status: Literal["no_feasible_found_in_budget"]
    optimality_proven: Literal[False] = False


class InfeasibleOptimizeResponse(OptimizeResponseBase):
    status: Literal["infeasible_proven"]
    optimality_proven: Literal[True] = True
    conflicts: list[RequirementConflict]


class UnsupportedOptimizeResponse(OptimizeResponseBase):
    status: Literal["unsupported"]
    optimality_proven: Literal[False] = False


class FieldIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    code: str
    message: str


OptimizeResponse = Annotated[
    FeasibleOptimizeResponse
    | InconclusiveOptimizeResponse
    | InfeasibleOptimizeResponse
    | UnsupportedOptimizeResponse,
    Field(discriminator="status"),
]


class ValidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    ruleset_id: str
    supported: bool
    issues: list[FieldIssue]
    warnings: list[str]
