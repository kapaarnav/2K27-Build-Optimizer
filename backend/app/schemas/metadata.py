from pydantic import BaseModel, ConfigDict, Field

from app.domain import BadgeTier, BuildType, Importance, Position
from app.rules.manifest import PositionCoverage


class PlaystyleOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str


class AttributeDescriptor(BaseModel):
    """Present so clients have a typed attribute dictionary. Empty until rules are verified."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    category: str


class UnlockDescriptor(BaseModel):
    """Verified unlock id. The label repeats the id because no display name is stored."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str


class MetadataResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ruleset_id: str
    game: str
    scoring_version: str
    optimizer_version: str
    files_sha256: str
    disclaimer: str
    recommendations_enabled: bool
    positions: list[Position]
    build_types: list[BuildType]
    importance_levels: list[Importance]
    playstyles: list[PlaystyleOption]
    attributes: list[AttributeDescriptor]
    badges: list[UnlockDescriptor]
    animations: list[UnlockDescriptor]
    takeovers: list[UnlockDescriptor]
    badge_tiers: list[BadgeTier]
    coverage: list[PositionCoverage]
    notes: list[str] = Field(default_factory=list)
