"""Orchestrate one locked-body search and its status.

Infeasible is used only when a relaxation proves the request contradicts
verified bounds, the link closure, required unlocks, or a non-negative Cap
Breaker gain. A miss that the relaxation still allows is unsupported: the
verified tables do not contain a recipe, and that is not a proof the game
forbids the request.
"""

import logging
import time
from dataclasses import dataclass
from typing import Literal

from app.domain import (
    OPTIMIZER_VERSION,
    SCORING_VERSION,
    Importance,
    SearchMode,
    VerificationStatus,
)
from app.optimizer.cpsat import (
    SearchSpace,
    SolveClassification,
    VerifiedVector,
    relaxation_status,
    solve_exact,
)
from app.optimizer.validator import validate_recipe
from app.rules.engine import (
    BodyQuery,
    application_limit,
    archetype_name,
    assess_body,
    assess_bounds,
    audit_request,
    exact_overall,
    propagate_links,
    query_from_body,
    required_target_conflict,
)
from app.rules.loader import ActiveRuleset
from app.rules.models import BadgeRule, BodyProfile, EligibilityRule, RuleBundle
from app.schemas.optimize import (
    AttributeRating,
    BuildMeasurements,
    CacheInfo,
    CapBreakerAllocation,
    CoverageReport,
    FeasibleOptimizeResponse,
    InconclusiveOptimizeResponse,
    InfeasibleOptimizeResponse,
    OptimizeRequest,
    OptimizeResponse,
    Recommendation,
    RecommendationSet,
    RequirementConflict,
    ScoreBreakdown,
    UnsupportedOptimizeResponse,
)

logger = logging.getLogger(__name__)

StatusName = Literal[
    "complete_proven",
    "partial_feasible",
    "infeasible_proven",
    "no_feasible_found_in_budget",
    "unsupported",
]

_NOT_ILLEGAL = "This is not a proof the request is illegal."
_TIER_RANK = {"bronze": 0, "silver": 1, "gold": 2, "hall_of_fame": 3}


@dataclass(frozen=True)
class SolveBudget:
    max_time_seconds: float = 2.0
    deadline: float | None = None

    def expired(self) -> bool:
        return self.deadline is not None and time.monotonic() >= self.deadline


@dataclass(frozen=True)
class Outcome:
    status: StatusName
    optimality_proven: bool
    warnings: tuple[str, ...]
    notes: tuple[str, ...]
    missing_mechanics: tuple[str, ...]
    conflicts: tuple[RequirementConflict, ...]
    recommendation: Recommendation | None


@dataclass(frozen=True)
class _Prepared:
    space: SearchSpace
    spendable: int
    can_raise: frozenset[str]
    reference_base: dict[str, int] | None
    reference_apps: dict[str, int] | None


def solve_locked_body(
    bundle: RuleBundle,
    request: OptimizeRequest,
    budget: SolveBudget | None = None,
) -> Outcome:
    limit = budget or SolveBudget()
    prepared = _prepare(bundle, request)
    if isinstance(prepared, Outcome):
        return prepared
    if limit.expired():
        return _inconclusive()
    hit = solve_exact(
        bundle,
        request,
        prepared.space,
        spendable=prepared.spendable,
        max_time_seconds=limit.max_time_seconds,
        reference_base=prepared.reference_base,
        reference_apps=prepared.reference_apps,
    )
    if hit.classification is SolveClassification.infeasible:
        return _classify_infeasible(bundle, request, prepared, limit)
    if hit.classification is SolveClassification.inconclusive or hit.candidate is None:
        return _inconclusive()
    check = validate_recipe(bundle, request, prepared.space.query, hit.candidate)
    if check.problems:
        logger.error("Validator rejected solver candidate: %s", "; ".join(check.problems))
        raise RuntimeError("Independent validation rejected the solver recipe.")
    proven = hit.classification is SolveClassification.proven
    build_type, position, height_in, weight_lb, wingspan_in = prepared.space.query.key()
    recommendation = Recommendation(
        build_id="ephemeral-1",
        name=hit.candidate.name,
        rank=1,
        score=check.score,
        body=BuildMeasurements(
            build_type=build_type,
            position=position,
            height_in=height_in,
            weight_lb=weight_lb,
            wingspan_in=wingspan_in,
        ),
        base_attributes=_ratings(prepared.space.attribute_ids, hit.candidate.base),
        final_attributes=_ratings(prepared.space.attribute_ids, hit.candidate.final),
        cap_breaker_allocations=[
            CapBreakerAllocation(
                pool_id=item.pool_id,
                attribute_id=item.attribute_id,
                applications=item.applications,
                rating_gain=item.rating_gain,
            )
            for item in hit.candidate.allocations
        ],
        eligible_badges=list(check.badges),
        eligible_animations=list(check.animations),
        eligible_takeovers=list(check.takeovers),
        score_breakdown=ScoreBreakdown(
            scoring_version=SCORING_VERSION,
            components=list(check.components),
        ),
        deviations=list(check.deviations),
        verification="verified",
    )
    warnings = _success_warnings(
        proven=proven,
        synthetic=bundle.any_synthetic(),
        refined=prepared.reference_base is not None,
    )
    return Outcome(
        status="complete_proven" if proven else "partial_feasible",
        optimality_proven=proven,
        warnings=warnings,
        notes=warnings[:1],
        missing_mechanics=(),
        conflicts=(),
        recommendation=recommendation,
    )


def response_from_outcome(
    outcome: Outcome,
    ruleset: ActiveRuleset,
    request_id: str,
    elapsed_ms: int,
) -> OptimizeResponse:
    shared = {
        "request_id": request_id,
        "ruleset_id": ruleset.manifest.ruleset_id,
        "scoring_version": SCORING_VERSION,
        "optimizer_version": OPTIMIZER_VERSION,
        "elapsed_ms": elapsed_ms,
        "coverage": CoverageReport(
            supported=outcome.status != "unsupported",
            notes=list(outcome.notes),
            missing_mechanics=list(outcome.missing_mechanics),
        ),
        "warnings": list(outcome.warnings),
        "cache": CacheInfo(hit=False),
        "recommendations": RecommendationSet(
            top=[outcome.recommendation] if outcome.recommendation is not None else []
        ),
    }
    if outcome.status in ("complete_proven", "partial_feasible"):
        return FeasibleOptimizeResponse(
            **shared,
            status=outcome.status,
            optimality_proven=outcome.optimality_proven,
        )
    if outcome.status == "no_feasible_found_in_budget":
        return InconclusiveOptimizeResponse(**shared, status="no_feasible_found_in_budget")
    if outcome.status == "infeasible_proven":
        return InfeasibleOptimizeResponse(
            **shared,
            status="infeasible_proven",
            conflicts=list(outcome.conflicts),
        )
    return UnsupportedOptimizeResponse(**shared, status="unsupported")


def _prepare(bundle: RuleBundle, request: OptimizeRequest) -> _Prepared | Outcome:
    query = query_from_body(request.body)
    if not query.fully_locked():
        return _unsupported(
            (
                "Single-body search needs build type, position, height, weight, and "
                "wingspan locked. Unlocked measurements stay preferences, and other "
                "bodies were not searched.",
            ),
            ("body_profiles",),
        )
    body_finding = assess_body(bundle, query)
    if body_finding.code != "body_legal":
        if body_finding.legal is False:
            return _infeasible((RequirementConflict(field="body", message=body_finding.message),))
        return _unsupported((body_finding.message,), (body_finding.mechanic,))

    blocking = [finding for finding in audit_request(bundle, request) if finding.blocks_request()]
    if blocking:
        return _unsupported(
            tuple(finding.message for finding in blocking),
            tuple(finding.mechanic for finding in blocking),
        )

    profile = _profile(bundle, query)
    attribute_ids = bundle.verified_attribute_ids()
    bounds = {item.attribute_id: (item.minimum, item.maximum) for item in profile.attribute_bounds}
    missing_bounds = [attr for attr in attribute_ids if attr not in bounds]
    if missing_bounds:
        listed = ", ".join(missing_bounds)
        return _unsupported(
            (
                f"No verified rating bounds are loaded for {listed}. "
                f"Those ratings were not judged legal or illegal. {_NOT_ILLEGAL}",
            ),
            ("body_profiles",),
        )

    unlock_gap = _unlock_gap(bundle, request, query)
    if unlock_gap is not None:
        return unlock_gap

    catalog = set(attribute_ids)
    unknown = [
        attr
        for attr in (
            *request.cap_breakers.forbidden_attribute_ids,
            *(item.attribute_id for item in request.cap_breakers.minimum_allocations),
        )
        if attr not in catalog
    ]
    if unknown:
        listed = ", ".join(sorted(set(unknown)))
        return _unsupported(
            (f"{listed} is not in the verified attribute catalog. {_NOT_ILLEGAL}",),
            ("attribute_costs",),
        )

    forbidden = set(request.cap_breakers.forbidden_attribute_ids)
    for item in request.cap_breakers.minimum_allocations:
        if item.count > 0 and item.attribute_id in forbidden:
            return _infeasible(
                (
                    RequirementConflict(
                        field=f"cap_breakers.{item.attribute_id}",
                        message=(
                            f"{item.attribute_id} is forbidden and also has a minimum "
                            f"allocation of {item.count}."
                        ),
                    ),
                )
            )

    reference = _reference(bundle, request, query, attribute_ids)
    if isinstance(reference, Outcome):
        return reference
    reference_base, reference_apps = reference

    vectors = _vectors(bundle, query, attribute_ids)
    if not vectors:
        return _unsupported(
            (
                "No verified overall and archetype name for this locked body meet the "
                f"request. Nothing was estimated. {_NOT_ILLEGAL}",
            ),
            ("attribute_costs", "archetype_names"),
        )

    available = sum(pool.available for pool in request.cap_breakers.pools)
    spendable = available - request.cap_breakers.reserved_total
    can_raise = frozenset(attr for attr in attribute_ids if spendable > 0 and attr not in forbidden)
    limit = application_limit(bundle)
    permissions = frozenset(
        (item.category, item.attribute_id)
        for item in bundle.cap_breakers.specialization_permissions
        if item.status is VerificationStatus.verified
    )
    gains = [
        step
        for step in bundle.cap_breakers.gain_steps
        if step.status is VerificationStatus.verified
    ]
    return _Prepared(
        space=SearchSpace(
            query=query,
            profile=profile,
            attribute_ids=attribute_ids,
            bounds=bounds,
            vectors=vectors,
            gains=gains,
            permissions=permissions,
            application_limit=limit.limit,
        ),
        spendable=spendable,
        can_raise=can_raise,
        reference_base=reference_base,
        reference_apps=reference_apps,
    )


def _classify_infeasible(
    bundle: RuleBundle,
    request: OptimizeRequest,
    prepared: _Prepared,
    budget: SolveBudget,
) -> Outcome:
    if budget.expired():
        return _inconclusive()
    status = relaxation_status(
        bundle,
        request,
        prepared.space,
        can_raise=set(prepared.can_raise),
        max_time_seconds=budget.max_time_seconds,
    )
    if status is SolveClassification.inconclusive:
        return _inconclusive()
    if status is not SolveClassification.infeasible:
        return _unsupported(
            (
                "No verified base vector and Cap Breaker step meet the request. "
                f"An unobserved step was not treated as +1. {_NOT_ILLEGAL}",
            ),
            ("attribute_costs", "cap_breakers"),
        )
    conflicts = _explain(bundle, request, prepared)
    return _infeasible(tuple(conflicts))


def _explain(
    bundle: RuleBundle,
    request: OptimizeRequest,
    prepared: _Prepared,
) -> list[RequirementConflict]:
    conflicts: list[RequirementConflict] = []
    bounds = prepared.space.bounds
    for target in request.attribute_targets:
        if target.importance is not Importance.required:
            continue
        lower, upper = bounds[target.id]
        if target.target < lower:
            conflicts.append(
                RequirementConflict(
                    field=f"attribute_targets.{target.id}",
                    message=(
                        f"{target.id} was requested at {target.target}. "
                        f"The verified minimum on this body is {lower}, "
                        "and a Cap Breaker cannot lower a rating."
                    ),
                )
            )
        elif target.target > upper and target.id not in prepared.can_raise:
            conflicts.append(
                RequirementConflict(
                    field=f"attribute_targets.{target.id}",
                    message=(
                        f"{target.id} was requested at {target.target}. "
                        f"The verified maximum on this body is {upper}, "
                        "and no Cap Breaker can be spent on it."
                    ),
                )
            )
    conflicts.extend(_pin_conflicts(bundle, request, prepared.space))
    if not prepared.can_raise:
        conflicts.extend(_link_conflicts(bundle, request, prepared.space))
    if conflicts:
        return conflicts
    return [
        RequirementConflict(
            field="attribute_targets",
            message=(
                "The required ratings and unlocks contradict the verified bounds "
                "and link closure for this body. A Cap Breaker cannot lower a rating."
            ),
        )
    ]


def _pin_conflicts(
    bundle: RuleBundle,
    request: OptimizeRequest,
    space: SearchSpace,
) -> list[RequirementConflict]:
    conflicts: list[RequirementConflict] = []
    pinned = {
        target.id: target.target
        for target in request.attribute_targets
        if target.importance is Importance.required
    }
    groups: list[tuple[str, list[EligibilityRule], str | None]] = []
    for badge in request.badges:
        if badge.importance is not Importance.required:
            continue
        rules = [
            rule
            for rule in bundle.eligibility.badges
            if rule.id == badge.id
            and rule.status is VerificationStatus.verified
            and rule.covers_body(space.query.key())
            and _TIER_RANK[rule.tier.value] >= _TIER_RANK[badge.minimum_tier.value]
        ]
        groups.append((f"badges.{badge.id}", rules, badge.minimum_tier.value))
    for animation in request.animations:
        if animation.importance is not Importance.required:
            continue
        rules = [
            rule
            for rule in bundle.eligibility.animations
            if rule.id == animation.id
            and rule.status is VerificationStatus.verified
            and rule.covers_body(space.query.key())
        ]
        groups.append((f"animations.{animation.id}", rules, None))
    for takeover in request.takeovers:
        if takeover.importance is not Importance.required:
            continue
        rules = [
            rule
            for rule in bundle.eligibility.takeovers
            if rule.id == takeover.id
            and rule.status is VerificationStatus.verified
            and rule.covers_body(space.query.key())
        ]
        groups.append((f"takeovers.{takeover.id}", rules, None))
    for field, rules, tier in groups:
        if not rules:
            continue
        blocks = [_rule_block(rule, pinned) for rule in rules]
        if any(block is None for block in blocks):
            continue
        detail = blocks[0] or "the verified predicate is not met"
        label = f" at {tier}" if tier else ""
        conflicts.append(
            RequirementConflict(
                field=field,
                message=f"{field}{label} cannot be met because {detail}.",
            )
        )
    return conflicts


def _rule_block(rule: EligibilityRule, pinned: dict[str, int]) -> str | None:
    pins = [
        f"{item.attribute_id} is required at {pinned[item.attribute_id]} "
        f"and the predicate needs {item.minimum}"
        for item in rule.requirements
        if item.attribute_id in pinned and pinned[item.attribute_id] < item.minimum
    ]
    if not pins:
        return None
    return "; ".join(pins)


def _link_conflicts(
    bundle: RuleBundle,
    request: OptimizeRequest,
    space: SearchSpace,
) -> list[RequirementConflict]:
    required = {
        target.id: target.target
        for target in request.attribute_targets
        if target.importance is Importance.required
    }
    if not required:
        return []
    ratings = {attr: space.bounds[attr][0] for attr in space.attribute_ids}
    for attribute_id, target in required.items():
        ratings[attribute_id] = target
    if any(
        target < space.bounds[attr][0] or target > space.bounds[attr][1]
        for attr, target in ratings.items()
    ):
        return []
    finding = required_target_conflict(bundle, ratings, required)
    if finding.code != "required_target_conflict":
        return []
    return [RequirementConflict(field="links", message=finding.message)]


def _unlock_gap(bundle: RuleBundle, request: OptimizeRequest, query: BodyQuery) -> Outcome | None:
    for badge in request.badges:
        gap = _predicate_gap(query, badge.id, "badge", bundle.eligibility.badges)
        if gap is not None:
            return gap
        rules = [
            rule
            for rule in bundle.eligibility.badges
            if isinstance(rule, BadgeRule)
            and rule.id == badge.id
            and rule.status is VerificationStatus.verified
            and rule.covers_body(query.key())
        ]
        if not any(
            _TIER_RANK[rule.tier.value] >= _TIER_RANK[badge.minimum_tier.value] for rule in rules
        ):
            return _unsupported(
                (
                    f"Badge {badge.id} has no verified {badge.minimum_tier.value} "
                    f"or higher predicate for this body. {_NOT_ILLEGAL}",
                ),
                ("badge_eligibility",),
            )
    for animation in request.animations:
        gap = _predicate_gap(query, animation.id, "animation", bundle.eligibility.animations)
        if gap is not None:
            return gap
    for takeover in request.takeovers:
        gap = _predicate_gap(query, takeover.id, "takeover", bundle.eligibility.takeovers)
        if gap is not None:
            return gap
    return None


def _predicate_gap(
    query: BodyQuery,
    unlock_id: str,
    kind: str,
    rules: list[EligibilityRule],
) -> Outcome | None:
    covering = [
        rule
        for rule in rules
        if rule.id == unlock_id
        and rule.status is VerificationStatus.verified
        and rule.covers_body(query.key())
    ]
    if covering:
        return None
    mechanic = {
        "badge": "badge_eligibility",
        "animation": "animations",
        "takeover": "takeovers",
    }[kind]
    label = {"badge": "Badge", "animation": "Animation", "takeover": "Takeover"}[kind]
    return _unsupported(
        (
            f"{label} {unlock_id} has no verified eligibility rule for this body. "
            f"Unsupported means the rule is missing, which is different from being "
            f"ineligible. {_NOT_ILLEGAL}",
        ),
        (mechanic,),
    )


def _reference(
    bundle: RuleBundle,
    request: OptimizeRequest,
    query: BodyQuery,
    attribute_ids: list[str],
) -> tuple[dict[str, int] | None, dict[str, int] | None] | Outcome:
    del bundle
    if request.mode is not SearchMode.refine:
        return None, None
    reference = request.reference
    if reference is None:
        return _unsupported(("Refine mode needs a reference build.",), ("body_profiles",))
    same_body = (
        reference.body.build_type is query.build_type
        and reference.body.position is query.position
        and reference.body.height_in == query.height_in
        and reference.body.weight_lb == query.weight_lb
        and reference.body.wingspan_in == query.wingspan_in
    )
    if not same_body:
        return _unsupported(
            (
                "The reference body is not the locked body. This version searches only "
                "that locked body, so other bodies were not judged legal or illegal.",
            ),
            ("body_profiles",),
        )
    ratings = {item.id: item.rating for item in reference.base_attributes}
    if set(ratings) != set(attribute_ids):
        return _unsupported(
            (
                "The reference ratings do not match the verified attribute catalog, "
                f"so refine stability was not applied. {_NOT_ILLEGAL}",
            ),
            ("attribute_costs",),
        )
    apps: dict[str, int] = dict.fromkeys(attribute_ids, 0)
    for allocation in reference.cap_breaker_allocations:
        if allocation.attribute_id not in apps:
            return _unsupported(
                (
                    f"{allocation.attribute_id} is not in the verified attribute catalog. "
                    f"{_NOT_ILLEGAL}",
                ),
                ("cap_breakers",),
            )
        apps[allocation.attribute_id] += allocation.applications
    return ratings, apps


def _vectors(
    bundle: RuleBundle,
    query: BodyQuery,
    attribute_ids: list[str],
) -> list[VerifiedVector]:
    vectors: list[VerifiedVector] = []
    seen: set[tuple[tuple[str, int], ...]] = set()
    for observation in bundle.costs.observations:
        if observation.status is not VerificationStatus.verified:
            continue
        if observation.body_key() != query.key():
            continue
        ratings = observation.rating_map()
        if set(ratings) != set(attribute_ids):
            continue
        identity = tuple(sorted(ratings.items()))
        if identity in seen:
            continue
        if assess_bounds(bundle, query, ratings).code != "attributes_within_bounds":
            continue
        propagated = propagate_links(bundle, ratings)
        if propagated.status != "verified":
            continue
        fixed = {item.attribute_id: item.rating for item in propagated.ratings}
        if fixed != ratings:
            continue
        named = archetype_name(bundle, query, ratings)
        priced = exact_overall(bundle, query, ratings)
        if named.name is None or priced.overall is None:
            continue
        seen.add(identity)
        vectors.append(VerifiedVector(base=ratings, overall=priced.overall, name=named.name))
    return vectors


def _profile(bundle: RuleBundle, query: BodyQuery) -> BodyProfile:
    profile = next(
        (
            body
            for body in bundle.bodies.bodies
            if body.status is VerificationStatus.verified and body.tuple_key == query.key()
        ),
        None,
    )
    if profile is None:
        raise RuntimeError("A legal body is missing its profile.")
    return profile


def _ratings(attribute_ids: list[str], ratings: dict[str, int]) -> list[AttributeRating]:
    return [
        AttributeRating(id=attribute_id, rating=ratings[attribute_id])
        for attribute_id in attribute_ids
    ]


def _success_warnings(*, proven: bool, synthetic: bool, refined: bool) -> tuple[str, ...]:
    if proven:
        lead = "Optimum is proven for the verified recipes of this locked body."
    else:
        lead = (
            "A verified recipe was found, and the search ended before optimality "
            "was proven for this locked body."
        )
    warnings = [lead, "Playstyle did not change this result."]
    if refined:
        warnings.append(
            "The reference body was kept, and reference ratings were preferred "
            "after requested targets."
        )
    if synthetic:
        warnings.append(
            "Synthetic rules produced this recipe. It is not an NBA 2K27 recommendation."
        )
    return tuple(warnings)


def _unsupported(messages: tuple[str, ...], mechanics: tuple[str, ...]) -> Outcome:
    missing = tuple(dict.fromkeys(mechanics))
    return Outcome(
        status="unsupported",
        optimality_proven=False,
        warnings=messages,
        notes=messages,
        missing_mechanics=missing,
        conflicts=(),
        recommendation=None,
    )


def _infeasible(conflicts: tuple[RequirementConflict, ...]) -> Outcome:
    warning = (
        "Verified rules prove this request cannot be met. "
        "A closest build is not searched in this version."
    )
    return Outcome(
        status="infeasible_proven",
        optimality_proven=True,
        warnings=(warning,),
        notes=("The request contradicts verified rules for this locked body.",),
        missing_mechanics=(),
        conflicts=conflicts,
        recommendation=None,
    )


def _inconclusive() -> Outcome:
    message = (
        "No verified recipe was found before the search budget ended. "
        "The search did not prove the request is illegal."
    )
    return Outcome(
        status="no_feasible_found_in_budget",
        optimality_proven=False,
        warnings=(message,),
        notes=(message,),
        missing_mechanics=(),
        conflicts=(),
        recommendation=None,
    )
