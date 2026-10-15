from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain import (
    IDENTIFIER_PATTERN,
    MECHANIC_FIELDS,
    BadgeTier,
    BuildType,
    Position,
    VerificationStatus,
)
from app.rules.manifest import RulesManifest
from app.rules.provenance import Provenance, Sourced, require_verified_evidence

# File sanity bounds. They are not in-game legal ranges.
_RATING = Field(ge=0, le=150)
_INCHES = Field(ge=1, le=150)
_POUNDS = Field(ge=1, le=1000)


class AttributeDefinition(Sourced):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    label: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=80)


class AttributesFile(BaseModel):
    """Canonical attribute dictionary. Empty until names are sourced."""

    model_config = ConfigDict(extra="forbid")

    catalog_complete: bool = False
    attributes: list[AttributeDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def catalog_is_explicit(self) -> Self:
        ids = [item.id for item in self.attributes]
        if len(ids) != len(set(ids)):
            raise ValueError("Attribute ids must be unique.")
        if self.catalog_complete:
            if not self.attributes:
                raise ValueError("A complete attribute catalog needs at least one attribute.")
            if any(item.status is not VerificationStatus.verified for item in self.attributes):
                raise ValueError(
                    "A complete attribute catalog can contain only verified attributes."
                )
        return self

    def verified_ids(self) -> list[str]:
        return [item.id for item in self.attributes if item.status is VerificationStatus.verified]


class AttributeBound(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attribute_id: str = Field(pattern=IDENTIFIER_PATTERN)
    minimum: int = _RATING
    maximum: int = _RATING

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.minimum > self.maximum:
            raise ValueError("Attribute bound minimum cannot exceed maximum.")
        return self


class BodyProfile(Sourced):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    build_type: BuildType
    position: Position
    height_in: int = _INCHES
    weight_lb: int = _POUNDS
    wingspan_in: int = _INCHES
    attribute_bounds: list[AttributeBound] = Field(default_factory=list)

    @property
    def tuple_key(self) -> tuple[BuildType, Position, int, int, int]:
        return (self.build_type, self.position, self.height_in, self.weight_lb, self.wingspan_in)


class BodyCoverageEntry(Sourced):
    build_type: BuildType
    position: Position
    enumeration: str = Field(pattern=r"^(complete|partial)$")

    @model_validator(mode="after")
    def complete_is_verified(self) -> Self:
        if self.enumeration == "complete" and self.status is not VerificationStatus.verified:
            raise ValueError("A complete body list has to be verified.")
        return self


class BodiesFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body_coverage: list[BodyCoverageEntry] = Field(default_factory=list)
    bodies: list[BodyProfile] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_bodies(self) -> Self:
        ids = [item.id for item in self.bodies]
        if len(ids) != len(set(ids)):
            raise ValueError("Body ids must be unique.")
        keys = [item.tuple_key for item in self.bodies]
        if len(keys) != len(set(keys)):
            raise ValueError("Body measurements must be unique.")
        coverage_keys = [(item.build_type, item.position) for item in self.body_coverage]
        if len(coverage_keys) != len(set(coverage_keys)):
            raise ValueError("Body coverage must use each build type and position once.")
        return self


class RatingEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=IDENTIFIER_PATTERN)
    rating: int = _RATING


class LinkRule(Sourced):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    source_attribute_id: str = Field(pattern=IDENTIFIER_PATTERN)
    target_attribute_id: str = Field(pattern=IDENTIFIER_PATTERN)
    when_source_at_least: int = _RATING
    target_minimum: int = _RATING

    @model_validator(mode="after")
    def distinct_attributes(self) -> Self:
        if self.source_attribute_id == self.target_attribute_id:
            raise ValueError("A link needs two different attributes.")
        return self


class LinkTable(BaseModel):
    """A closure is applied only when it is explicitly complete and verified."""

    model_config = ConfigDict(extra="forbid")

    complete: bool = False
    status: VerificationStatus = VerificationStatus.unsupported
    synthetic: bool = False
    provenance: Provenance | None = None
    links: list[LinkRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def closure_is_explicit(self) -> Self:
        ids = [item.id for item in self.links]
        if len(ids) != len(set(ids)):
            raise ValueError("Link ids must be unique.")
        verified = self.status is VerificationStatus.verified
        if self.complete != verified:
            raise ValueError("Link closure is complete only when its status is verified.")
        if verified:
            if self.provenance is None:
                raise ValueError("A verified link closure needs provenance.")
            require_verified_evidence(self.provenance)
            if any(item.status is not VerificationStatus.verified for item in self.links):
                raise ValueError("A verified link closure can contain only verified links.")
        return self


class VectorRule(Sourced):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    build_type: BuildType
    position: Position
    height_in: int = _INCHES
    weight_lb: int = _POUNDS
    wingspan_in: int = _INCHES
    base_attributes: list[RatingEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ratings(self) -> Self:
        ids = [item.id for item in self.base_attributes]
        if len(ids) != len(set(ids)):
            raise ValueError("Attribute ratings must be unique.")
        return self

    def rating_map(self) -> dict[str, int]:
        return {item.id: item.rating for item in self.base_attributes}

    def body_key(self) -> tuple[BuildType, Position, int, int, int]:
        return (self.build_type, self.position, self.height_in, self.weight_lb, self.wingspan_in)


class CostObservation(VectorRule):
    overall: int = _RATING


class ArchetypeNameRule(VectorRule):
    name: str = Field(min_length=1, max_length=120)


class CostsFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observations: list[CostObservation] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        _unique_ids([item.id for item in self.observations], "Cost observation ids must be unique.")
        return self


class NamesFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    names: list[ArchetypeNameRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        _unique_ids([item.id for item in self.names], "Archetype name ids must be unique.")
        return self


class AttributeMinimum(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attribute_id: str = Field(pattern=IDENTIFIER_PATTERN)
    minimum: int = _RATING


class BodyRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    build_type: BuildType
    position: Position
    height_in: int = _INCHES
    weight_lb: int = _POUNDS
    wingspan_in: int = _INCHES

    def key(self) -> tuple[BuildType, Position, int, int, int]:
        return (self.build_type, self.position, self.height_in, self.weight_lb, self.wingspan_in)


class EligibilityRule(Sourced):
    rule_id: str = Field(pattern=IDENTIFIER_PATTERN)
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    applies_to: str = Field(pattern=r"^(base|final)$")
    requirements: list[AttributeMinimum] = Field(min_length=1)
    body_scope: str = Field(pattern=r"^(any|listed)$")
    bodies: list[BodyRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def scope_matches_bodies(self) -> Self:
        if self.body_scope == "any" and self.bodies:
            raise ValueError("A rule with body scope 'any' cannot list bodies.")
        if self.body_scope == "listed" and not self.bodies:
            raise ValueError("A listed body scope needs at least one body.")
        requirement_ids = [item.attribute_id for item in self.requirements]
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ValueError("Eligibility requirements must use each attribute once.")
        return self

    def covers_position(self, position: Position) -> bool:
        if self.body_scope == "any":
            return True
        return any(body.position is position for body in self.bodies)

    def covers_body(self, key: tuple[BuildType, Position, int, int, int]) -> bool:
        if self.body_scope == "any":
            return True
        return any(body.key() == key for body in self.bodies)


class BadgeRule(EligibilityRule):
    tier: BadgeTier


class UnlockRule(EligibilityRule):
    pass


class EligibilityFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    badges: list[BadgeRule] = Field(default_factory=list)
    animations: list[UnlockRule] = Field(default_factory=list)
    takeovers: list[UnlockRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_rule_ids(self) -> Self:
        _unique_ids([item.rule_id for item in self.badges], "Badge rule ids must be unique.")
        _unique_ids(
            [item.rule_id for item in self.animations],
            "Animation rule ids must be unique.",
        )
        _unique_ids(
            [item.rule_id for item in self.takeovers],
            "Takeover rule ids must be unique.",
        )
        return self


class GainStep(Sourced):
    rule_id: str = Field(pattern=IDENTIFIER_PATTERN)
    attribute_id: str = Field(pattern=IDENTIFIER_PATTERN)
    starting_rating: int = _RATING
    applications: int = Field(ge=1, le=100)
    rating_gain: int = _RATING


class ApplicationLimit(Sourced):
    limit: int = Field(ge=0, le=100)


class SpecializationPermission(Sourced):
    rule_id: str = Field(pattern=IDENTIFIER_PATTERN)
    category: str = Field(min_length=1, max_length=80)
    attribute_id: str = Field(pattern=IDENTIFIER_PATTERN)


class CapBreakerFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_applications: ApplicationLimit | None = None
    gain_steps: list[GainStep] = Field(default_factory=list)
    specialization_permissions: list[SpecializationPermission] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_steps(self) -> Self:
        _unique_ids([item.rule_id for item in self.gain_steps], "Gain step ids must be unique.")
        _unique_ids(
            [item.rule_id for item in self.specialization_permissions],
            "Specialization permission ids must be unique.",
        )
        steps = [
            (item.attribute_id, item.starting_rating, item.applications) for item in self.gain_steps
        ]
        if len(steps) != len(set(steps)):
            raise ValueError("Gain steps must be unique for each attribute, start, and count.")
        permissions = [
            (item.category, item.attribute_id) for item in self.specialization_permissions
        ]
        if len(permissions) != len(set(permissions)):
            raise ValueError("Specialization permissions must be unique.")
        return self


class RuleBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attributes: AttributesFile = Field(default_factory=AttributesFile)
    bodies: BodiesFile = Field(default_factory=BodiesFile)
    links: LinkTable = Field(default_factory=LinkTable)
    costs: CostsFile = Field(default_factory=CostsFile)
    names: NamesFile = Field(default_factory=NamesFile)
    eligibility: EligibilityFile = Field(default_factory=EligibilityFile)
    cap_breakers: CapBreakerFile = Field(default_factory=CapBreakerFile)

    def verified_attribute_ids(self) -> list[str]:
        return self.attributes.verified_ids()

    def links_evaluable(self) -> bool:
        table = self.links
        return table.complete and table.status is VerificationStatus.verified

    def any_synthetic(self) -> bool:
        sourced: list[Sourced | LinkTable | ApplicationLimit] = []
        if self.links.synthetic or any(item.synthetic for item in self.links.links):
            return True
        sourced.extend(self.attributes.attributes)
        sourced.extend(self.bodies.body_coverage)
        sourced.extend(self.bodies.bodies)
        sourced.extend(self.costs.observations)
        sourced.extend(self.names.names)
        sourced.extend(self.eligibility.badges)
        sourced.extend(self.eligibility.animations)
        sourced.extend(self.eligibility.takeovers)
        sourced.extend(self.cap_breakers.gain_steps)
        sourced.extend(self.cap_breakers.specialization_permissions)
        if self.cap_breakers.max_applications is not None:
            sourced.append(self.cap_breakers.max_applications)
        return any(item.synthetic for item in sourced)

    def mechanic_is_backed(self, position: Position, mechanic: str) -> bool:
        if mechanic == "body_profiles":
            return any(
                body.status is VerificationStatus.verified
                and body.position is position
                and self.coverage_entry(body.build_type, position) is not None
                for body in self.bodies.bodies
            )
        if mechanic == "attribute_costs":
            return any(
                item.status is VerificationStatus.verified and item.position is position
                for item in self.costs.observations
            )
        if mechanic == "cap_breakers":
            return any(
                item.status is VerificationStatus.verified for item in self.cap_breakers.gain_steps
            )
        if mechanic == "badge_eligibility":
            return any(
                item.status is VerificationStatus.verified and item.covers_position(position)
                for item in self.eligibility.badges
            )
        if mechanic == "animations":
            return any(
                item.status is VerificationStatus.verified and item.covers_position(position)
                for item in self.eligibility.animations
            )
        if mechanic == "takeovers":
            return any(
                item.status is VerificationStatus.verified and item.covers_position(position)
                for item in self.eligibility.takeovers
            )
        if mechanic == "archetype_names":
            return any(
                item.status is VerificationStatus.verified and item.position is position
                for item in self.names.names
            )
        raise ValueError(f"Unknown mechanic {mechanic}.")

    def coverage_entry(self, build_type: BuildType, position: Position) -> BodyCoverageEntry | None:
        for entry in self.bodies.body_coverage:
            if (
                entry.build_type is build_type
                and entry.position is position
                and entry.status is VerificationStatus.verified
            ):
                return entry
        return None


def ensure_consistent(bundle: RuleBundle, manifest: RulesManifest) -> None:
    catalog = set(bundle.verified_attribute_ids())
    _references_use_catalog(bundle, catalog)
    _vectors_match_catalog(bundle, catalog)
    _bodies_have_coverage(bundle)
    for entry in manifest.coverage:
        for mechanic in MECHANIC_FIELDS:
            if getattr(entry, mechanic) is not VerificationStatus.verified:
                continue
            if not bundle.mechanic_is_backed(entry.position, mechanic):
                raise ValueError(
                    f"{entry.position.value} marks {mechanic} verified "
                    "but no verified records back it."
                )
    if manifest.fully_verified_positions():
        if not bundle.attributes.catalog_complete:
            raise ValueError("Fully verified coverage needs a complete attribute catalog.")
        if not bundle.links_evaluable():
            raise ValueError("Fully verified coverage needs a verified link closure.")


def _unique_ids(values: list[str], message: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(message)


def _references_use_catalog(bundle: RuleBundle, catalog: set[str]) -> None:
    referenced: list[str] = []
    for body in bundle.bodies.bodies:
        referenced.extend(bound.attribute_id for bound in body.attribute_bounds)
    for link in bundle.links.links:
        referenced.extend([link.source_attribute_id, link.target_attribute_id])
    for rule in (
        *bundle.eligibility.badges,
        *bundle.eligibility.animations,
        *bundle.eligibility.takeovers,
    ):
        referenced.extend(item.attribute_id for item in rule.requirements)
    referenced.extend(step.attribute_id for step in bundle.cap_breakers.gain_steps)
    referenced.extend(item.attribute_id for item in bundle.cap_breakers.specialization_permissions)
    unknown = sorted(set(referenced) - catalog)
    if unknown:
        raise ValueError(f"Rules reference attributes that are not in the catalog: {unknown}.")


def _vectors_match_catalog(bundle: RuleBundle, catalog: set[str]) -> None:
    if not bundle.attributes.catalog_complete and (
        any(item.status is VerificationStatus.verified for item in bundle.costs.observations)
        or any(item.status is VerificationStatus.verified for item in bundle.names.names)
    ):
        raise ValueError("Exact cost and name rows need a complete attribute catalog.")
    for item in (*bundle.costs.observations, *bundle.names.names):
        if item.status is not VerificationStatus.verified:
            continue
        ids = {rating.id for rating in item.base_attributes}
        if ids != catalog:
            raise ValueError(
                f"{item.id} must list exactly the verified attribute catalog, with no extras."
            )


def _bodies_have_coverage(bundle: RuleBundle) -> None:
    for body in bundle.bodies.bodies:
        if body.status is not VerificationStatus.verified:
            continue
        entry = bundle.coverage_entry(body.build_type, body.position)
        if entry is None:
            raise ValueError(f"Verified body {body.id} has no verified coverage entry.")
    for entry in bundle.bodies.body_coverage:
        if entry.enumeration != "complete":
            continue
        matched = [
            body
            for body in bundle.bodies.bodies
            if body.build_type is entry.build_type and body.position is entry.position
        ]
        if not matched:
            raise ValueError(
                f"Complete body coverage for {entry.build_type.value} {entry.position.value} "
                "needs at least one body."
            )
