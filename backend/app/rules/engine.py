from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain import BadgeTier, BuildType, Position, VerificationStatus
from app.rules.models import (
    ArchetypeNameRule,
    BadgeRule,
    BodyProfile,
    CostObservation,
    EligibilityRule,
    RuleBundle,
    VectorRule,
)
from app.schemas.common import BodyInput
from app.schemas.optimize import OptimizeRequest

FindingStatus = Literal["verified", "unsupported", "contradictory", "ineligible"]
BodyKey = tuple[BuildType, Position, int, int, int]

_TIER_ORDER = (
    BadgeTier.bronze,
    BadgeTier.silver,
    BadgeTier.gold,
    BadgeTier.hall_of_fame,
)


class BodyQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    build_type: BuildType | None = None
    position: Position | None = None
    height_in: int | None = None
    weight_lb: int | None = None
    wingspan_in: int | None = None
    build_type_locked: bool = False
    position_locked: bool = False
    height_locked: bool = False
    weight_locked: bool = False
    wingspan_locked: bool = False

    def fully_locked(self) -> bool:
        return bool(
            self.build_type_locked
            and self.position_locked
            and self.height_locked
            and self.weight_locked
            and self.wingspan_locked
            and self.build_type is not None
            and self.position is not None
            and self.height_in is not None
            and self.weight_lb is not None
            and self.wingspan_in is not None
        )

    def key(self) -> BodyKey:
        if not self.fully_locked():
            raise RuntimeError("A partial body has no exact key.")
        assert self.build_type is not None
        assert self.position is not None
        assert self.height_in is not None
        assert self.weight_lb is not None
        assert self.wingspan_in is not None
        return (
            self.build_type,
            self.position,
            self.height_in,
            self.weight_lb,
            self.wingspan_in,
        )


class ForcedMinimum(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attribute_id: str
    minimum: int


class PropagatedRating(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attribute_id: str
    rating: int


class RuleFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    mechanic: str
    status: FindingStatus
    code: str
    message: str
    legal: bool | None = None
    overall: int | None = None
    name: str | None = None
    eligible: bool | None = None
    highest_tier: BadgeTier | None = None
    rating_gain: int | None = None
    limit: int | None = None
    allowed: bool | None = None
    forced_minima: list[ForcedMinimum] = Field(default_factory=list)
    ratings: list[PropagatedRating] = Field(default_factory=list)

    def blocks_request(self) -> bool:
        if self.legal is False:
            return True
        return self.status != "verified"


def query_from_body(body: BodyInput) -> BodyQuery:
    return BodyQuery(
        build_type=body.build_type.value,
        position=body.position.value,
        height_in=body.height_in.value,
        weight_lb=body.weight_lb.value,
        wingspan_in=body.wingspan_in.value,
        build_type_locked=body.build_type.locked,
        position_locked=body.position.locked,
        height_locked=body.height_in.locked,
        weight_locked=body.weight_lb.locked,
        wingspan_locked=body.wingspan_in.locked,
    )


def assess_body(bundle: RuleBundle, query: BodyQuery) -> RuleFinding:
    verified_bodies = [
        body for body in bundle.bodies.bodies if body.status is VerificationStatus.verified
    ]
    if not verified_bodies:
        return RuleFinding(
            field="body",
            mechanic="body_profiles",
            status="unsupported",
            code="body_profiles_unverified",
            message=(
                "No verified body profiles are loaded. This body was not judged legal or illegal."
            ),
        )
    if not query.fully_locked():
        return RuleFinding(
            field="body",
            mechanic="body_profiles",
            status="unsupported",
            code="body_not_fully_specified",
            message=(
                "The body is not fully locked. Unlocked measurements stay preferences, "
                "and this request was not judged legal or illegal."
            ),
        )
    key = query.key()
    match = next((body for body in verified_bodies if body.tuple_key == key), None)
    if match is not None:
        return RuleFinding(
            field="body",
            mechanic="body_profiles",
            status="verified",
            code="body_legal",
            legal=True,
            message=f"{_describe(key)} is in the verified body list.",
        )
    coverage = bundle.coverage_entry(key[0], key[1])
    described = _describe(key)
    if coverage is not None and coverage.enumeration == "complete":
        return RuleFinding(
            field="body",
            mechanic="body_profiles",
            status="verified",
            code="body_not_legal",
            legal=False,
            message=f"{described} contradicts the verified body list.",
        )
    if coverage is not None:
        return RuleFinding(
            field="body",
            mechanic="body_profiles",
            status="unsupported",
            code="body_not_in_partial_coverage",
            message=(
                f"{described} is absent from a partial verified body list, "
                "so it was not judged legal or illegal."
            ),
        )
    return RuleFinding(
        field="body",
        mechanic="body_profiles",
        status="unsupported",
        code="body_coverage_missing",
        message=(
            f"{described} has no verified body coverage, so it was not judged legal or illegal."
        ),
    )


def assess_bounds(bundle: RuleBundle, query: BodyQuery, ratings: dict[str, int]) -> RuleFinding:
    body_finding = assess_body(bundle, query)
    if body_finding.code != "body_legal":
        return body_finding
    profile = _matching_body(bundle, query.key())
    assert profile is not None
    incomplete = _incomplete_ratings(bundle, ratings)
    if incomplete is not None:
        return incomplete
    bounds = {item.attribute_id: item for item in profile.attribute_bounds}
    missing = [attribute_id for attribute_id in ratings if attribute_id not in bounds]
    if missing:
        listed = ", ".join(sorted(missing))
        return RuleFinding(
            field="body",
            mechanic="body_profiles",
            status="unsupported",
            code="attribute_bounds_unverified",
            message=(
                f"No verified rating bounds are loaded for {listed}. "
                "Those ratings were not judged legal or illegal."
            ),
        )
    outside = [
        attribute_id
        for attribute_id, rating in ratings.items()
        if rating < bounds[attribute_id].minimum or rating > bounds[attribute_id].maximum
    ]
    if outside:
        listed = ", ".join(sorted(outside))
        return RuleFinding(
            field="body",
            mechanic="body_profiles",
            status="verified",
            code="attribute_out_of_bounds",
            legal=False,
            message=f"{listed} contradicts the verified rating bounds for this body.",
        )
    return RuleFinding(
        field="body",
        mechanic="body_profiles",
        status="verified",
        code="attributes_within_bounds",
        legal=True,
        message="The supplied ratings are inside the verified bounds for this body.",
    )


def propagate_links(bundle: RuleBundle, ratings: dict[str, int]) -> RuleFinding:
    if not bundle.links_evaluable():
        return RuleFinding(
            field="links",
            mechanic="linked_attributes",
            status="unsupported",
            code="linked_attributes_unverified",
            message=(
                "Linked attributes are not a verified closure, so ratings were not propagated."
            ),
        )
    incomplete = _incomplete_ratings(bundle, ratings)
    if incomplete is not None:
        return incomplete
    current = dict(ratings)
    forced: dict[str, int] = {}
    for _ in range(len(bundle.links.links) + 1):
        changed = False
        for link in bundle.links.links:
            source = current[link.source_attribute_id]
            target = current[link.target_attribute_id]
            if source >= link.when_source_at_least and target < link.target_minimum:
                current[link.target_attribute_id] = link.target_minimum
                forced[link.target_attribute_id] = link.target_minimum
                changed = True
        if not changed:
            return RuleFinding(
                field="links",
                mechanic="linked_attributes",
                status="verified",
                code="links_applied",
                message="Verified link closure applied.",
                forced_minima=_forced_list(forced),
                ratings=_rating_list(current),
            )
    return RuleFinding(
        field="links",
        mechanic="linked_attributes",
        status="contradictory",
        code="link_cycle",
        message="The verified link closure did not reach a fixed point.",
    )


def required_target_conflict(
    bundle: RuleBundle,
    ratings: dict[str, int],
    required: dict[str, int],
) -> RuleFinding:
    propagated = propagate_links(bundle, ratings)
    if propagated.status != "verified":
        return propagated
    achieved = {item.attribute_id: item.rating for item in propagated.ratings}
    forced = {item.attribute_id: item.minimum for item in propagated.forced_minima}
    conflicts = [
        (attribute_id, required[attribute_id], achieved[attribute_id])
        for attribute_id in required
        if attribute_id in forced and achieved[attribute_id] != required[attribute_id]
    ]
    if not conflicts:
        return RuleFinding(
            field="links",
            mechanic="linked_attributes",
            status="verified",
            code="required_targets_hold",
            message="Required ratings still hold after the verified link closure.",
            forced_minima=propagated.forced_minima,
            ratings=propagated.ratings,
        )
    detail = "; ".join(
        f"{attribute_id} was requested at {requested} and the link closure forces {actual}"
        for attribute_id, requested, actual in conflicts
    )
    return RuleFinding(
        field="links",
        mechanic="linked_attributes",
        status="contradictory",
        code="required_target_conflict",
        message=f"{detail}. A required exact rating cannot be raised.",
        forced_minima=propagated.forced_minima,
        ratings=propagated.ratings,
    )


def exact_overall(bundle: RuleBundle, query: BodyQuery, ratings: dict[str, int]) -> RuleFinding:
    return _exact_vector(
        bundle,
        query,
        ratings,
        records=[
            item for item in bundle.costs.observations if item.status is VerificationStatus.verified
        ],
        empty_code="attribute_costs_unverified",
        empty_message=(
            "No verified overall observations are loaded, so overall was not calculated."
        ),
        missing_code="cost_not_observed",
        missing_message=(
            "This exact body and attribute vector has no verified overall observation. "
            "Overall was not estimated."
        ),
        mechanic="attribute_costs",
        field="attribute_costs",
    )


def archetype_name(bundle: RuleBundle, query: BodyQuery, ratings: dict[str, int]) -> RuleFinding:
    finding = _exact_vector(
        bundle,
        query,
        ratings,
        records=[item for item in bundle.names.names if item.status is VerificationStatus.verified],
        empty_code="archetype_names_unverified",
        empty_message="No verified archetype names are loaded, so no name was assigned.",
        missing_code="archetype_name_not_observed",
        missing_message=(
            "This exact body and attribute vector has no verified archetype name. "
            "A name was not generated."
        ),
        mechanic="archetype_names",
        field="archetype_names",
    )
    if finding.status != "verified":
        return finding
    matched = _matching_vector(
        [item for item in bundle.names.names if item.status is VerificationStatus.verified],
        query.key(),
        ratings,
    )
    if not isinstance(matched, ArchetypeNameRule):
        raise RuntimeError("A matched archetype row was missing its name.")
    return finding.model_copy(
        update={
            "code": "archetype_name_matched",
            "name": matched.name,
            "message": matched.name,
        }
    )


def badge_eligibility(
    bundle: RuleBundle,
    badge_id: str,
    ratings: dict[str, int],
    phase: str,
    query: BodyQuery,
) -> RuleFinding:
    rules = [
        rule
        for rule in bundle.eligibility.badges
        if rule.id == badge_id and rule.status is VerificationStatus.verified
    ]
    if not rules:
        return _missing_unlock("badges", badge_id, "badge_eligibility", "Badge")
    return _tier_eligibility(bundle, rules, ratings, phase, query, badge_id)


def animation_eligibility(
    bundle: RuleBundle,
    animation_id: str,
    ratings: dict[str, int],
    phase: str,
    query: BodyQuery,
) -> RuleFinding:
    rules = [
        rule
        for rule in bundle.eligibility.animations
        if rule.id == animation_id and rule.status is VerificationStatus.verified
    ]
    if not rules:
        return _missing_unlock("animations", animation_id, "animations", "Animation")
    return _unlock_eligibility(bundle, rules, ratings, phase, query, "animations", animation_id)


def takeover_eligibility(
    bundle: RuleBundle,
    takeover_id: str,
    ratings: dict[str, int],
    phase: str,
    query: BodyQuery,
) -> RuleFinding:
    rules = [
        rule
        for rule in bundle.eligibility.takeovers
        if rule.id == takeover_id and rule.status is VerificationStatus.verified
    ]
    if not rules:
        return _missing_unlock("takeovers", takeover_id, "takeovers", "Takeover")
    return _unlock_eligibility(bundle, rules, ratings, phase, query, "takeovers", takeover_id)


def cap_breaker_gain(
    bundle: RuleBundle,
    attribute_id: str,
    starting_rating: int,
    applications: int,
) -> RuleFinding:
    steps = [
        step
        for step in bundle.cap_breakers.gain_steps
        if step.status is VerificationStatus.verified
    ]
    if not steps:
        return RuleFinding(
            field="cap_breakers",
            mechanic="cap_breakers",
            status="unsupported",
            code="cap_breakers_unverified",
            message=(
                "No verified Cap Breaker gain steps are loaded, so the gain was not calculated."
            ),
        )
    matched = next(
        (
            step
            for step in steps
            if step.attribute_id == attribute_id
            and step.starting_rating == starting_rating
            and step.applications == applications
        ),
        None,
    )
    if matched is None:
        return RuleFinding(
            field="cap_breakers",
            mechanic="cap_breakers",
            status="unsupported",
            code="cap_breaker_step_not_observed",
            message=(
                f"No verified gain is recorded for {attribute_id} at {starting_rating} "
                f"after {applications} application(s). The gain was not assumed to be +1 "
                "per application."
            ),
        )
    return RuleFinding(
        field="cap_breakers",
        mechanic="cap_breakers",
        status="verified",
        code="cap_breaker_gain_matched",
        rating_gain=matched.rating_gain,
        message=(
            f"{applications} application(s) from {starting_rating} grant +{matched.rating_gain}."
        ),
    )


def application_limit(bundle: RuleBundle) -> RuleFinding:
    limit = bundle.cap_breakers.max_applications
    if limit is None or limit.status is not VerificationStatus.verified:
        return RuleFinding(
            field="cap_breakers",
            mechanic="cap_breakers",
            status="unsupported",
            code="cap_breaker_limit_unverified",
            message="The per-attribute Cap Breaker application limit is not verified.",
        )
    return RuleFinding(
        field="cap_breakers",
        mechanic="cap_breakers",
        status="verified",
        code="cap_breaker_limit_matched",
        limit=limit.limit,
        message=f"The verified application limit is {limit.limit}.",
    )


def specialization_permission(
    bundle: RuleBundle,
    category: str,
    attribute_id: str,
) -> RuleFinding:
    permissions = [
        item
        for item in bundle.cap_breakers.specialization_permissions
        if item.status is VerificationStatus.verified
    ]
    if not permissions:
        return RuleFinding(
            field="cap_breakers",
            mechanic="cap_breakers",
            status="unsupported",
            code="specialization_unverified",
            message=(
                "No verified specialization permissions are loaded, "
                "so this category was not judged allowed or disallowed."
            ),
        )
    matched = next(
        (
            item
            for item in permissions
            if item.category == category and item.attribute_id == attribute_id
        ),
        None,
    )
    if matched is None:
        return RuleFinding(
            field="cap_breakers",
            mechanic="cap_breakers",
            status="unsupported",
            code="specialization_not_observed",
            message=(
                f"No verified permission says {category} can be spent on {attribute_id}. "
                "That is unsupported, which is different from the game forbidding it."
            ),
        )
    return RuleFinding(
        field="cap_breakers",
        mechanic="cap_breakers",
        status="verified",
        code="specialization_allowed",
        allowed=True,
        message=f"{category} can be spent on {attribute_id} under the verified permission.",
    )


def audit_request(bundle: RuleBundle, request: OptimizeRequest) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    attribute_finding = _audit_attributes(bundle, request)
    if attribute_finding is not None:
        findings.append(attribute_finding)
    body_finding = _audit_body(bundle, request.body)
    if body_finding is not None:
        findings.append(body_finding)
    if not bundle.links_evaluable():
        findings.append(
            RuleFinding(
                field="links",
                mechanic="linked_attributes",
                status="unsupported",
                code="linked_attributes_unverified",
                message=(
                    "Linked attributes are not a verified closure, "
                    "so they were not applied to this request."
                ),
            )
        )
    if not any(item.status is VerificationStatus.verified for item in bundle.costs.observations):
        findings.append(
            RuleFinding(
                field="attribute_costs",
                mechanic="attribute_costs",
                status="unsupported",
                code="attribute_costs_unverified",
                message=(
                    "No verified overall observations are loaded, so overall was not calculated."
                ),
            )
        )
    if not any(item.status is VerificationStatus.verified for item in bundle.names.names):
        findings.append(
            RuleFinding(
                field="archetype_names",
                mechanic="archetype_names",
                status="unsupported",
                code="archetype_names_unverified",
                message="No verified archetype names are loaded, so no name was assigned.",
            )
        )
    verified_steps = [
        item
        for item in bundle.cap_breakers.gain_steps
        if item.status is VerificationStatus.verified
    ]
    if not verified_steps:
        findings.append(
            RuleFinding(
                field="cap_breakers",
                mechanic="cap_breakers",
                status="unsupported",
                code="cap_breakers_unverified",
                message=(
                    "No verified Cap Breaker gain steps are loaded, "
                    "so breaker allocations were not checked."
                ),
            )
        )
    for badge in request.badges:
        if not _has_unlock(bundle.eligibility.badges, badge.id):
            findings.append(_missing_unlock("badges", badge.id, "badge_eligibility", "Badge"))
    for animation in request.animations:
        if not _has_unlock(bundle.eligibility.animations, animation.id):
            findings.append(_missing_unlock("animations", animation.id, "animations", "Animation"))
    for takeover in request.takeovers:
        if not _has_unlock(bundle.eligibility.takeovers, takeover.id):
            findings.append(_missing_unlock("takeovers", takeover.id, "takeovers", "Takeover"))
    return findings


def _audit_attributes(bundle: RuleBundle, request: OptimizeRequest) -> RuleFinding | None:
    catalog = set(bundle.verified_attribute_ids())
    requested = [item.id for item in request.attribute_targets]
    if not bundle.attributes.catalog_complete or not catalog:
        listed = ", ".join(requested)
        return RuleFinding(
            field="attribute_targets",
            mechanic="attribute_costs",
            status="unsupported",
            code="attribute_catalog_unverified",
            message=(
                "No complete verified attribute catalog is loaded, so "
                f"{listed} were not matched to in-game attributes."
            ),
        )
    unknown = [attribute_id for attribute_id in requested if attribute_id not in catalog]
    if unknown:
        listed = ", ".join(unknown)
        return RuleFinding(
            field="attribute_targets",
            mechanic="attribute_costs",
            status="unsupported",
            code="unknown_attribute",
            message=f"{listed} is not in the verified attribute catalog.",
        )
    return None


def _audit_body(bundle: RuleBundle, body: BodyInput) -> RuleFinding | None:
    verified = [item for item in bundle.bodies.bodies if item.status is VerificationStatus.verified]
    if not verified:
        return assess_body(bundle, query_from_body(body))
    query = query_from_body(body)
    if not query.fully_locked():
        return None
    finding = assess_body(bundle, query)
    if finding.code == "body_legal":
        return None
    return finding


def _exact_vector(
    bundle: RuleBundle,
    query: BodyQuery,
    ratings: dict[str, int],
    records: list[VectorRule],
    empty_code: str,
    empty_message: str,
    missing_code: str,
    missing_message: str,
    mechanic: str,
    field: str,
) -> RuleFinding:
    if not records:
        return RuleFinding(
            field=field,
            mechanic=mechanic,
            status="unsupported",
            code=empty_code,
            message=empty_message,
        )
    if not query.fully_locked():
        return RuleFinding(
            field=field,
            mechanic=mechanic,
            status="unsupported",
            code="body_not_fully_specified",
            message="An exact lookup needs a fully specified body.",
        )
    incomplete = _incomplete_ratings(bundle, ratings)
    if incomplete is not None:
        return incomplete
    matched = _matching_vector(records, query.key(), ratings)
    if matched is None:
        return RuleFinding(
            field=field,
            mechanic=mechanic,
            status="unsupported",
            code=missing_code,
            message=missing_message,
        )
    return RuleFinding(
        field=field,
        mechanic=mechanic,
        status="verified",
        code="exact_vector_matched",
        overall=matched.overall if isinstance(matched, CostObservation) else None,
        message="Exact verified observation matched.",
    )


def _tier_eligibility(
    bundle: RuleBundle,
    rules: list[BadgeRule],
    ratings: dict[str, int],
    phase: str,
    query: BodyQuery,
    badge_id: str,
) -> RuleFinding:
    scoped = _scoped_rules(
        bundle,
        list(rules),
        ratings,
        phase,
        query,
        "badges",
        "badge_eligibility",
    )
    if isinstance(scoped, RuleFinding):
        return scoped
    badge_rules = [rule for rule in scoped if isinstance(rule, BadgeRule)]
    met = [rule for rule in badge_rules if _requirements_met(rule, ratings)]
    if not met:
        return RuleFinding(
            field=f"badges.{badge_id}",
            mechanic="badge_eligibility",
            status="ineligible",
            code="badge_requirements_unmet",
            eligible=False,
            message=(
                f"Badge {badge_id} has a verified predicate, and these ratings do not meet it."
            ),
        )
    best = max(met, key=lambda rule: _TIER_ORDER.index(rule.tier))
    return RuleFinding(
        field=f"badges.{badge_id}",
        mechanic="badge_eligibility",
        status="verified",
        code="badge_eligible",
        eligible=True,
        highest_tier=best.tier,
        message=f"Badge {badge_id} is eligible through {best.tier.value}.",
    )


def _unlock_eligibility(
    bundle: RuleBundle,
    rules: list[EligibilityRule],
    ratings: dict[str, int],
    phase: str,
    query: BodyQuery,
    mechanic: str,
    unlock_id: str,
) -> RuleFinding:
    field = f"{mechanic}.{unlock_id}"
    scoped = _scoped_rules(bundle, rules, ratings, phase, query, field, mechanic)
    if isinstance(scoped, RuleFinding):
        return scoped
    if any(_requirements_met(rule, ratings) for rule in scoped):
        return RuleFinding(
            field=field,
            mechanic=mechanic,
            status="verified",
            code="unlock_eligible",
            eligible=True,
            message=f"{unlock_id} is eligible under a verified predicate.",
        )
    return RuleFinding(
        field=field,
        mechanic=mechanic,
        status="ineligible",
        code="unlock_requirements_unmet",
        eligible=False,
        message=f"{unlock_id} has a verified predicate, and these ratings do not meet it.",
    )


def _scoped_rules(
    bundle: RuleBundle,
    rules: list[EligibilityRule],
    ratings: dict[str, int],
    phase: str,
    query: BodyQuery,
    field: str,
    mechanic: str,
) -> list[EligibilityRule] | RuleFinding:
    if not query.fully_locked():
        return RuleFinding(
            field=field,
            mechanic=mechanic,
            status="unsupported",
            code="body_not_fully_specified",
            message="Eligibility needs a fully specified body.",
        )
    incomplete = _incomplete_ratings(bundle, ratings)
    if incomplete is not None:
        return incomplete
    applicable = [
        rule for rule in rules if rule.applies_to == phase and rule.covers_body(query.key())
    ]
    if not applicable:
        return RuleFinding(
            field=field,
            mechanic=mechanic,
            status="unsupported",
            code="eligibility_not_verified_for_body",
            message=(
                "No verified eligibility predicate covers this body and phase. "
                "That is unsupported, which is different from being ineligible."
            ),
        )
    return applicable


def _requirements_met(rule: EligibilityRule, ratings: dict[str, int]) -> bool:
    return all(ratings[item.attribute_id] >= item.minimum for item in rule.requirements)


def _missing_unlock(field_prefix: str, unlock_id: str, mechanic: str, label: str) -> RuleFinding:
    return RuleFinding(
        field=f"{field_prefix}.{unlock_id}",
        mechanic=mechanic,
        status="unsupported",
        code=_unlock_code(field_prefix),
        message=(
            f"{label} {unlock_id} has no verified eligibility rule. "
            "Unsupported means the rule is missing, which is different from being ineligible."
        ),
    )


def _unlock_code(field_prefix: str) -> str:
    return {
        "badges": "badge_unverified",
        "animations": "animation_unverified",
        "takeovers": "takeover_unverified",
    }[field_prefix]


def _has_unlock(rules: list[EligibilityRule], unlock_id: str) -> bool:
    return any(
        rule.id == unlock_id and rule.status is VerificationStatus.verified for rule in rules
    )


def _incomplete_ratings(bundle: RuleBundle, ratings: dict[str, int]) -> RuleFinding | None:
    catalog = set(bundle.verified_attribute_ids())
    if set(ratings) != catalog:
        return RuleFinding(
            field="attribute_targets",
            mechanic="attribute_costs",
            status="unsupported",
            code="ratings_incomplete",
            message=(
                "The rating vector does not match the verified attribute catalog, "
                "so it was not evaluated."
            ),
        )
    return None


def _matching_body(bundle: RuleBundle, key: BodyKey) -> BodyProfile | None:
    return next(
        (
            body
            for body in bundle.bodies.bodies
            if body.status is VerificationStatus.verified and body.tuple_key == key
        ),
        None,
    )


def _matching_vector(
    records: list[VectorRule],
    key: BodyKey,
    ratings: dict[str, int],
) -> VectorRule | None:
    return next(
        (item for item in records if item.body_key() == key and item.rating_map() == ratings),
        None,
    )


def _describe(key: BodyKey) -> str:
    build_type, position, height_in, weight_lb, wingspan_in = key
    return (
        f"Locked {build_type.value} {position.value} "
        f"{height_in} in, {weight_lb} lb, {wingspan_in} in wingspan"
    )


def _forced_list(forced: dict[str, int]) -> list[ForcedMinimum]:
    return [
        ForcedMinimum(attribute_id=attribute_id, minimum=minimum)
        for attribute_id, minimum in sorted(forced.items())
    ]


def _rating_list(ratings: dict[str, int]) -> list[PropagatedRating]:
    return [
        PropagatedRating(attribute_id=attribute_id, rating=rating)
        for attribute_id, rating in sorted(ratings.items())
    ]
