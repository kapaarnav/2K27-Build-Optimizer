from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain import MECHANIC_FIELDS, Position, VerificationStatus


class PositionCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: Position
    body_profiles: VerificationStatus
    attribute_costs: VerificationStatus
    cap_breakers: VerificationStatus
    badge_eligibility: VerificationStatus
    animations: VerificationStatus
    takeovers: VerificationStatus
    archetype_names: VerificationStatus

    def missing_mechanics(self) -> list[str]:
        return [
            name
            for name in MECHANIC_FIELDS
            if getattr(self, name) is not VerificationStatus.verified
        ]

    def is_fully_verified(self) -> bool:
        return not self.missing_mechanics()


class RulesManifest(BaseModel):
    """Schema for the active rules file.

    Extra keys are rejected so numeric game data cannot be dropped into the
    manifest without an explicit schema change and review.
    """

    model_config = ConfigDict(extra="forbid")

    ruleset_id: str = Field(min_length=1, max_length=80)
    game: str = "nba2k27"
    observed_at: date | None = None
    source_app_version: str = "unknown"
    tuning_version: str = "unknown"
    verified_by: list[str] = Field(default_factory=list)
    synthetic: bool = False
    coverage: list[PositionCoverage] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_positions(self) -> "RulesManifest":
        positions = [entry.position for entry in self.coverage]
        if len(positions) != len(set(positions)):
            raise ValueError("Coverage entries must use each position once.")
        return self

    def fully_verified_positions(self) -> set[Position]:
        return {entry.position for entry in self.coverage if entry.is_fully_verified()}

    def coverage_for(self, position: Position) -> PositionCoverage | None:
        for entry in self.coverage:
            if entry.position is position:
                return entry
        return None
