from datetime import date
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain import VerificationStatus


class Provenance(BaseModel):
    """Where a rule came from. Verified rules need an observation date and evidence pointer."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=300)
    observed_at: date | None = None
    source_app_version: str = Field(default="unknown", min_length=1, max_length=80)
    evidence_ref: str | None = Field(default=None, min_length=1, max_length=300)
    notes: str = Field(default="", max_length=500)


def require_verified_evidence(provenance: Provenance) -> None:
    if provenance.observed_at is None:
        raise ValueError("A verified rule needs observed_at.")
    if provenance.evidence_ref is None:
        raise ValueError("A verified rule needs evidence_ref.")


class Sourced(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: VerificationStatus
    synthetic: bool = False
    provenance: Provenance

    @model_validator(mode="after")
    def verified_has_evidence(self) -> Self:
        if self.status is VerificationStatus.verified:
            require_verified_evidence(self.provenance)
        return self
