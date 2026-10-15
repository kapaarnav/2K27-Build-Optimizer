"""Recompute a recipe with the rules engine.

The checker does not read solver booleans. A recipe is accepted only when
bounds, links, overall, archetype name, Cap Breaker steps, pool budgets, and
unlock predicates all agree with the candidate.
"""

from collections import Counter
from dataclasses import dataclass

from app.domain import BadgeTier, Importance, PoolKind, VerificationStatus
from app.optimizer.scoring import (
    DISPLAY_NORMAL_RATING,
    DISPLAY_NORMAL_UNLOCK,
    DISPLAY_PRIORITIZED_RATING,
    DISPLAY_PRIORITIZED_UNLOCK,
    fit_score,
)
from app.rules.engine import (
    BodyQuery,
    animation_eligibility,
    application_limit,
    archetype_name,
    assess_bounds,
    badge_eligibility,
    cap_breaker_gain,
    exact_overall,
    propagate_links,
    specialization_permission,
    takeover_eligibility,
)
from app.rules.models import RuleBundle
from app.schemas.optimize import (
    DeviationNote,
    EligibleBadge,
    EligibleUnlock,
    OptimizeRequest,
    ScoreComponent,
)

_TIER_RANK = {
    BadgeTier.bronze: 0,
    BadgeTier.silver: 1,
    BadgeTier.gold: 2,
    BadgeTier.hall_of_fame: 3,
}


@dataclass(frozen=True)
class Allocation:
    pool_id: str
    attribute_id: str
    applications: int
    rating_gain: int


@dataclass(frozen=True)
class Candidate:
    base: dict[str, int]
    final: dict[str, int]
    allocations: tuple[Allocation, ...]
    name: str
    overall: int


@dataclass(frozen=True)
class RecipeCheck:
    problems: tuple[str, ...]
    badges: tuple[EligibleBadge, ...]
    animations: tuple[EligibleUnlock, ...]
    takeovers: tuple[EligibleUnlock, ...]
    deviations: tuple[DeviationNote, ...]
    overall: int | None
    score: float
    components: tuple[ScoreComponent, ...]
    prioritized_points: int
    normal_points: int
    prioritized_unlock_misses: int
    normal_unlock_misses: int
    applications_used: int


def validate_recipe(
    bundle: RuleBundle,
    request: OptimizeRequest,
    query: BodyQuery,
    candidate: Candidate,
) -> RecipeCheck:
    problems: list[str] = []
    catalog = bundle.verified_attribute_ids()
    _check_vectors(bundle, query, candidate, catalog, problems)
    _check_links(bundle, candidate, catalog, problems)
    overall = _check_overall_and_name(bundle, query, candidate, problems)
    _check_breakers(bundle, request, candidate, catalog, problems)
    _check_required_ratings(request, candidate, problems)

    badges = _eligible_badges(bundle, query, candidate)
    animations = _eligible_unlocks(
        bundle,
        query,
        candidate,
        bundle.eligibility.animations,
        animation_eligibility,
        "animations",
    )
    takeovers = _eligible_unlocks(
        bundle,
        query,
        candidate,
        bundle.eligibility.takeovers,
        takeover_eligibility,
        "takeovers",
    )
    deviations, prioritized_points, normal_points = _deviations(
        bundle,
        request,
        candidate,
        problems,
    )
    prioritized_misses, normal_misses = _unlock_misses(
        request,
        badges,
        animations,
        takeovers,
        problems,
    )
    applications = sum(item.applications for item in candidate.allocations)
    score = fit_score(
        prioritized_points=prioritized_points,
        normal_points=normal_points,
        prioritized_unlock_misses=prioritized_misses,
        normal_unlock_misses=normal_misses,
    )
    return RecipeCheck(
        problems=tuple(problems),
        badges=tuple(badges),
        animations=tuple(animations),
        takeovers=tuple(takeovers),
        deviations=tuple(deviations),
        overall=overall,
        score=score,
        components=_components(
            overall,
            prioritized_points,
            normal_points,
            prioritized_misses,
            normal_misses,
            applications,
        ),
        prioritized_points=prioritized_points,
        normal_points=normal_points,
        prioritized_unlock_misses=prioritized_misses,
        normal_unlock_misses=normal_misses,
        applications_used=applications,
    )


def _check_vectors(
    bundle: RuleBundle,
    query: BodyQuery,
    candidate: Candidate,
    catalog: list[str],
    problems: list[str],
) -> None:
    if set(candidate.base) != set(catalog) or set(candidate.final) != set(catalog):
        problems.append("The rating vector does not match the verified attribute catalog.")
        return
    finding = assess_bounds(bundle, query, candidate.base)
    if finding.code != "attributes_within_bounds":
        problems.append(finding.message)


def _check_links(
    bundle: RuleBundle,
    candidate: Candidate,
    catalog: list[str],
    problems: list[str],
) -> None:
    if set(candidate.base) != set(catalog):
        return
    finding = propagate_links(bundle, candidate.base)
    if finding.status != "verified":
        problems.append(finding.message)
        return
    propagated = {item.attribute_id: item.rating for item in finding.ratings}
    if propagated != candidate.base:
        problems.append("Base ratings are not a fixed point of the verified link closure.")


def _check_overall_and_name(
    bundle: RuleBundle,
    query: BodyQuery,
    candidate: Candidate,
    problems: list[str],
) -> int | None:
    if set(candidate.base) != set(bundle.verified_attribute_ids()):
        return None
    priced = exact_overall(bundle, query, candidate.base)
    named = archetype_name(bundle, query, candidate.base)
    if priced.overall is None:
        problems.append(priced.message)
    elif priced.overall != candidate.overall:
        problems.append(
            f"Overall {candidate.overall} does not match the verified observation {priced.overall}."
        )
    if named.name is None:
        problems.append(named.message)
    elif named.name != candidate.name:
        problems.append(
            f"Archetype name {candidate.name} does not match the verified name {named.name}."
        )
    return priced.overall


def _check_breakers(
    bundle: RuleBundle,
    request: OptimizeRequest,
    candidate: Candidate,
    catalog: list[str],
    problems: list[str],
) -> None:
    pools = {pool.id: pool for pool in request.cap_breakers.pools}
    forbidden = set(request.cap_breakers.forbidden_attribute_ids)
    spent = Counter[str]()
    gain_claimed = Counter[str]()
    per_pool = Counter[str]()
    for allocation in candidate.allocations:
        pool = pools.get(allocation.pool_id)
        if pool is None:
            problems.append(f"Allocation uses unknown pool {allocation.pool_id}.")
            continue
        if allocation.applications <= 0:
            problems.append("A Cap Breaker allocation needs a positive application count.")
            continue
        if allocation.attribute_id in forbidden:
            problems.append(f"{allocation.attribute_id} is forbidden and still received breakers.")
        if pool.kind is PoolKind.specialization:
            permission = specialization_permission(
                bundle,
                pool.category or "",
                allocation.attribute_id,
            )
            if permission.allowed is not True:
                problems.append(permission.message)
        spent[allocation.attribute_id] += allocation.applications
        gain_claimed[allocation.attribute_id] += allocation.rating_gain
        per_pool[allocation.pool_id] += allocation.applications

    for pool in request.cap_breakers.pools:
        if per_pool[pool.id] > pool.available:
            problems.append(f"Pool {pool.id} spends more than its available count.")
    available = sum(pool.available for pool in request.cap_breakers.pools)
    spendable = available - request.cap_breakers.reserved_total
    if sum(spent.values()) > spendable:
        problems.append("Cap Breaker allocations exceed the spendable total.")

    limit = application_limit(bundle)
    if limit.limit is not None:
        for attribute_id, count in spent.items():
            if count > limit.limit:
                problems.append(
                    f"{attribute_id} uses {count} applications. "
                    f"The verified limit is {limit.limit}."
                )

    minimums = {item.attribute_id: item.count for item in request.cap_breakers.minimum_allocations}
    for attribute_id, count in minimums.items():
        if spent[attribute_id] < count:
            problems.append(f"{attribute_id} received {spent[attribute_id]} of {count} required.")

    if set(candidate.base) != set(catalog) or set(candidate.final) != set(catalog):
        return
    for attribute_id in catalog:
        count = spent[attribute_id]
        claimed = gain_claimed[attribute_id]
        if count == 0:
            if claimed != 0:
                problems.append(f"{attribute_id} claims a gain without an allocation.")
            if candidate.final[attribute_id] != candidate.base[attribute_id]:
                problems.append(f"{attribute_id} changed without a Cap Breaker allocation.")
            continue
        finding = cap_breaker_gain(bundle, attribute_id, candidate.base[attribute_id], count)
        if finding.rating_gain is None:
            problems.append(finding.message)
            continue
        if claimed != finding.rating_gain:
            problems.append(
                f"{attribute_id} allocations claim +{claimed}, "
                f"and the verified step grants +{finding.rating_gain}."
            )
        expected = candidate.base[attribute_id] + finding.rating_gain
        if candidate.final[attribute_id] != expected:
            problems.append(
                f"{attribute_id} final {candidate.final[attribute_id]} "
                f"does not match base plus the verified gain ({expected})."
            )


def _check_required_ratings(
    request: OptimizeRequest,
    candidate: Candidate,
    problems: list[str],
) -> None:
    for target in request.attribute_targets:
        if target.importance is not Importance.required:
            continue
        achieved = candidate.final.get(target.id)
        if achieved != target.target:
            problems.append(
                f"{target.id} is required at {target.target} and the recipe has {achieved}."
            )


def _eligible_badges(
    bundle: RuleBundle,
    query: BodyQuery,
    candidate: Candidate,
) -> list[EligibleBadge]:
    ids = sorted(
        {
            rule.id
            for rule in bundle.eligibility.badges
            if rule.status is VerificationStatus.verified and rule.covers_body(query.key())
        }
    )
    eligible: list[EligibleBadge] = []
    for badge_id in ids:
        best: BadgeTier | None = None
        for phase in ("base", "final"):
            ratings = candidate.base if phase == "base" else candidate.final
            finding = badge_eligibility(bundle, badge_id, ratings, phase, query)
            if finding.highest_tier is None:
                continue
            if best is None or _TIER_RANK[finding.highest_tier] > _TIER_RANK[best]:
                best = finding.highest_tier
        if best is not None:
            eligible.append(EligibleBadge(id=badge_id, highest_tier=best))
    return eligible


def _eligible_unlocks(
    bundle: RuleBundle,
    query: BodyQuery,
    candidate: Candidate,
    rules: list,
    evaluate,
    mechanic: str,
) -> list[EligibleUnlock]:
    del mechanic
    ids = sorted(
        {
            rule.id
            for rule in rules
            if rule.status is VerificationStatus.verified and rule.covers_body(query.key())
        }
    )
    eligible: list[EligibleUnlock] = []
    for unlock_id in ids:
        for phase in ("base", "final"):
            ratings = candidate.base if phase == "base" else candidate.final
            finding = evaluate(bundle, unlock_id, ratings, phase, query)
            if finding.eligible is True:
                eligible.append(EligibleUnlock(id=unlock_id))
                break
    return eligible


def _deviations(
    bundle: RuleBundle,
    request: OptimizeRequest,
    candidate: Candidate,
    problems: list[str],
) -> tuple[list[DeviationNote], int, int]:
    notes: list[DeviationNote] = []
    prioritized = 0
    normal = 0
    for target in request.attribute_targets:
        if target.importance is Importance.required:
            continue
        achieved = candidate.final.get(target.id)
        if achieved is None or achieved == target.target:
            continue
        message = _deviation_message(bundle, candidate.base, target.id, target.target, achieved)
        notes.append(
            DeviationNote(
                attribute_id=target.id,
                requested=target.target,
                achieved=achieved,
                message=message,
            )
        )
        gap = abs(achieved - target.target)
        if target.importance is Importance.prioritized:
            prioritized += gap
        else:
            normal += gap
    if any(len(note.message) > 300 for note in notes):
        problems.append("A deviation note is too long to store.")
    return notes, prioritized, normal


def _deviation_message(
    bundle: RuleBundle,
    base: dict[str, int],
    attribute_id: str,
    requested: int,
    achieved: int,
) -> str:
    for link in bundle.links.links:
        if link.status is not VerificationStatus.verified:
            continue
        if link.target_attribute_id != attribute_id:
            continue
        source = base.get(link.source_attribute_id)
        if source is None:
            continue
        if source >= link.when_source_at_least and requested < link.target_minimum:
            return (
                f"{attribute_id} was requested at {requested}. "
                f"{link.source_attribute_id} at {source} forces {attribute_id} "
                f"to at least {link.target_minimum}. The recipe achieves {achieved}."
            )
    return f"{attribute_id} was requested at {requested} and the recipe achieves {achieved}."


def _unlock_misses(
    request: OptimizeRequest,
    badges: list[EligibleBadge],
    animations: list[EligibleUnlock],
    takeovers: list[EligibleUnlock],
    problems: list[str],
) -> tuple[int, int]:
    prioritized = 0
    normal = 0
    badge_by_id = {item.id: item for item in badges}
    for badge in request.badges:
        eligible = badge_by_id.get(badge.id)
        met = (
            eligible is not None
            and _TIER_RANK[eligible.highest_tier] >= _TIER_RANK[badge.minimum_tier]
        )
        prioritized, normal = _count_miss(
            met,
            badge.importance,
            f"Required badge {badge.id} is not eligible at {badge.minimum_tier.value}.",
            prioritized,
            normal,
            problems,
        )
    animation_ids = {item.id for item in animations}
    for animation in request.animations:
        prioritized, normal = _count_miss(
            animation.id in animation_ids,
            animation.importance,
            f"Required animation {animation.id} is not eligible.",
            prioritized,
            normal,
            problems,
        )
    takeover_ids = {item.id for item in takeovers}
    for takeover in request.takeovers:
        prioritized, normal = _count_miss(
            takeover.id in takeover_ids,
            takeover.importance,
            f"Required Takeover {takeover.id} is not eligible.",
            prioritized,
            normal,
            problems,
        )
    return prioritized, normal


def _count_miss(
    met: bool,
    importance: Importance,
    required_message: str,
    prioritized: int,
    normal: int,
    problems: list[str],
) -> tuple[int, int]:
    if met:
        return prioritized, normal
    if importance is Importance.required:
        problems.append(required_message)
    elif importance is Importance.prioritized:
        prioritized += 1
    else:
        normal += 1
    return prioritized, normal


def _components(
    overall: int | None,
    prioritized_points: int,
    normal_points: int,
    prioritized_misses: int,
    normal_misses: int,
    applications: int,
) -> tuple[ScoreComponent, ...]:
    return (
        ScoreComponent(
            id="observed_overall",
            weight=0,
            value=float(overall or 0),
            note="Exact verified overall for this base vector. It is not part of the fit score.",
        ),
        ScoreComponent(
            id="prioritized_deviation",
            weight=float(DISPLAY_PRIORITIZED_RATING),
            value=float(prioritized_points),
            note="Absolute miss on prioritized ratings, in rating points.",
        ),
        ScoreComponent(
            id="prioritized_unlock_miss",
            weight=float(DISPLAY_PRIORITIZED_UNLOCK),
            value=float(prioritized_misses),
            note="Prioritized badge, animation, or Takeover requests that were missed.",
        ),
        ScoreComponent(
            id="normal_deviation",
            weight=float(DISPLAY_NORMAL_RATING),
            value=float(normal_points),
            note="Absolute miss on normal ratings, in rating points.",
        ),
        ScoreComponent(
            id="normal_unlock_miss",
            weight=float(DISPLAY_NORMAL_UNLOCK),
            value=float(normal_misses),
            note="Normal badge, animation, or Takeover requests that were missed.",
        ),
        ScoreComponent(
            id="cap_breakers_used",
            weight=0,
            value=float(applications),
            note="Breaker count is minimized after targets. It does not change the fit score.",
        ),
    )
