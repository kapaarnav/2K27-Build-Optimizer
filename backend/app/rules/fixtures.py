from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain import BadgeTier, BuildType, Position
from app.rules.engine import (
    BodyQuery,
    RuleFinding,
    animation_eligibility,
    application_limit,
    archetype_name,
    assess_body,
    assess_bounds,
    badge_eligibility,
    cap_breaker_gain,
    exact_overall,
    propagate_links,
    required_target_conflict,
    specialization_permission,
    takeover_eligibility,
)
from app.rules.models import RuleBundle

Mechanic = Literal[
    "body",
    "bounds",
    "links",
    "required_conflict",
    "cost",
    "name",
    "badge",
    "animation",
    "takeover",
    "cap_breaker",
    "cap_limit",
    "specialization",
]


class FixtureBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    build_type: BuildType
    position: Position
    height_in: int
    weight_lb: int
    wingspan_in: int
    locked: bool = True

    def as_query(self) -> BodyQuery:
        return BodyQuery(
            build_type=self.build_type,
            position=self.position,
            height_in=self.height_in,
            weight_lb=self.weight_lb,
            wingspan_in=self.wingspan_in,
            build_type_locked=self.locked,
            position_locked=self.locked,
            height_locked=self.locked,
            weight_locked=self.locked,
            wingspan_locked=self.locked,
        )


class FixtureRating(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    rating: int


class FixtureExpect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["verified", "unsupported", "contradictory", "ineligible"]
    code: str
    legal: bool | None = None
    overall: int | None = None
    name: str | None = None
    eligible: bool | None = None
    highest_tier: BadgeTier | None = None
    rating_gain: int | None = None
    limit: int | None = None
    allowed: bool | None = None
    forced: dict[str, int] = Field(default_factory=dict)
    absent_words: list[str] = Field(default_factory=list)


class FixtureCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    mechanic: Mechanic
    body: FixtureBody | None = None
    ratings: list[FixtureRating] = Field(default_factory=list)
    required: list[FixtureRating] = Field(default_factory=list)
    badge_id: str | None = None
    animation_id: str | None = None
    takeover_id: str | None = None
    phase: Literal["base", "final"] = "final"
    attribute_id: str | None = None
    starting_rating: int | None = None
    applications: int | None = None
    category: str | None = None
    expect: FixtureExpect

    @model_validator(mode="after")
    def inputs_match_mechanic(self) -> Self:
        needs_body = {
            "body",
            "bounds",
            "cost",
            "name",
            "badge",
            "animation",
            "takeover",
        }
        needs_ratings = {
            "bounds",
            "links",
            "required_conflict",
            "cost",
            "name",
            "badge",
            "animation",
            "takeover",
        }
        if self.mechanic in needs_body and self.body is None:
            raise ValueError(f"{self.id} needs a body.")
        if self.mechanic in needs_ratings and not self.ratings:
            raise ValueError(f"{self.id} needs ratings.")
        if self.mechanic == "required_conflict" and not self.required:
            raise ValueError(f"{self.id} needs required ratings.")
        if self.mechanic == "badge" and self.badge_id is None:
            raise ValueError(f"{self.id} needs a badge id.")
        if self.mechanic == "animation" and self.animation_id is None:
            raise ValueError(f"{self.id} needs an animation id.")
        if self.mechanic == "takeover" and self.takeover_id is None:
            raise ValueError(f"{self.id} needs a takeover id.")
        if self.mechanic == "cap_breaker" and (
            self.attribute_id is None or self.starting_rating is None or self.applications is None
        ):
            raise ValueError(f"{self.id} needs an attribute, start rating, and application count.")
        if self.mechanic == "specialization" and (
            self.category is None or self.attribute_id is None
        ):
            raise ValueError(f"{self.id} needs a category and an attribute.")
        return self


class FixtureFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cases: list[FixtureCase] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        ids = [case.id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Fixture case ids must be unique.")
        return self


def evaluate_case(bundle: RuleBundle, case: FixtureCase) -> RuleFinding:
    ratings = {item.id: item.rating for item in case.ratings}
    required = {item.id: item.rating for item in case.required}
    query = case.body.as_query() if case.body is not None else BodyQuery()
    if case.mechanic == "body":
        return assess_body(bundle, query)
    if case.mechanic == "bounds":
        return assess_bounds(bundle, query, ratings)
    if case.mechanic == "links":
        return propagate_links(bundle, ratings)
    if case.mechanic == "required_conflict":
        return required_target_conflict(bundle, ratings, required)
    if case.mechanic == "cost":
        return exact_overall(bundle, query, ratings)
    if case.mechanic == "name":
        return archetype_name(bundle, query, ratings)
    if case.mechanic == "badge":
        assert case.badge_id is not None
        return badge_eligibility(bundle, case.badge_id, ratings, case.phase, query)
    if case.mechanic == "animation":
        assert case.animation_id is not None
        return animation_eligibility(bundle, case.animation_id, ratings, case.phase, query)
    if case.mechanic == "takeover":
        assert case.takeover_id is not None
        return takeover_eligibility(bundle, case.takeover_id, ratings, case.phase, query)
    if case.mechanic == "cap_breaker":
        assert case.attribute_id is not None
        assert case.starting_rating is not None
        assert case.applications is not None
        return cap_breaker_gain(
            bundle,
            case.attribute_id,
            case.starting_rating,
            case.applications,
        )
    if case.mechanic == "cap_limit":
        return application_limit(bundle)
    if case.mechanic == "specialization":
        assert case.category is not None
        assert case.attribute_id is not None
        return specialization_permission(bundle, case.category, case.attribute_id)
    raise RuntimeError(f"Unhandled mechanic {case.mechanic}.")
