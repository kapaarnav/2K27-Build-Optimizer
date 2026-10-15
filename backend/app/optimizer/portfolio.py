"""Search every verified body that matches the locks, then rank the recipes.

A measurement that is set but not locked is a preference. It breaks ties after
required, prioritized, and normal misses. It does not remove a body. A body is
dropped only when verified rules prove it cannot meet the request.

complete_proven means every matching body was solved or soundly pruned, and the
top five are the best of those proven results. A timeout never upgrades into
that claim. Closest builds are returned only after that proof, and a timeout
before the proof returns no closest build.
"""

import itertools
import logging
from dataclasses import dataclass
from typing import Literal

from app.domain import (
    SCORING_VERSION,
    BuildType,
    Importance,
    Position,
    SearchMode,
    VerificationStatus,
)
from app.optimizer.cpsat import SolveClassification, solve_exact
from app.optimizer.scoring import ALTERNATIVE_SCORE_BAND
from app.optimizer.solve import (
    Outcome,
    SolveBudget,
    _classify_infeasible,
    _inconclusive,
    _infeasible,
    _prepare,
    _ratings,
    _unsupported,
)
from app.optimizer.validator import Candidate, RecipeCheck, validate_recipe
from app.rules.engine import BodyQuery, assess_body, query_from_body
from app.rules.models import BodyProfile, RuleBundle
from app.schemas.common import (
    BodyInput,
    LockedBuildType,
    LockedInches,
    LockedPosition,
    LockedPounds,
)
from app.schemas.optimize import (
    BuildMeasurements,
    CapBreakerAllocation,
    OptimizeRequest,
    Recommendation,
    RequirementConflict,
    ScoreBreakdown,
    ScoreComponent,
    UnmetRequirement,
)

logger = logging.getLogger(__name__)

_TOP_K = 5
_ALTERNATIVE_LIMIT = 3
_PER_BODY_CAP = 5
_NOT_ILLEGAL = "This is not a proof the request is illegal."
_TIER_RANK = {"bronze": 0, "silver": 1, "gold": 2, "hall_of_fame": 3}

_Kind = Literal["recipes", "pruned", "unsupported", "timeout"]


@dataclass(frozen=True)
class Scored:
    key: tuple[int, ...]
    fingerprint: tuple[object, ...]
    profile: BodyProfile
    candidate: Candidate
    check: RecipeCheck
    physical_violations: int


@dataclass(frozen=True)
class _BodySearch:
    kind: _Kind
    profile: BodyProfile
    recipes: tuple[Scored, ...]
    exhausted: bool
    outcome: Outcome | None


def search_bodies(
    bundle: RuleBundle,
    request: OptimizeRequest,
    budget: SolveBudget | None = None,
) -> Outcome:
    limit = (budget or SolveBudget()).started()
    if limit.expired():
        return _inconclusive()

    refine_block = _refine_block(request)
    if refine_block is not None:
        return refine_block

    profiles = _matching_profiles(bundle, request, dropped=set())
    if not profiles:
        return _no_matching_body(bundle, request, limit)

    searches: list[_BodySearch] = []
    timed_out = False
    ordered = sorted(profiles, key=lambda profile: (_preference(request, profile), profile.id))
    for profile in ordered:
        if limit.expired():
            timed_out = True
            break
        searches.append(_search_profile(bundle, request, profile, limit, relax_required=False))

    return _assemble(bundle, request, limit, searches, timed_out, explored_all=not timed_out)


def _assemble(
    bundle: RuleBundle,
    request: OptimizeRequest,
    budget: SolveBudget,
    searches: list[_BodySearch],
    timed_out: bool,
    *,
    explored_all: bool,
) -> Outcome:
    recipes = [recipe for search in searches for recipe in search.recipes]
    unsupported = [search for search in searches if search.kind == "unsupported"]
    pruned = [search for search in searches if search.kind == "pruned"]
    unfinished = timed_out or any(
        search.kind == "timeout" or not search.exhausted for search in searches
    )
    scope_complete = _scope_complete(bundle, query_from_body(request.body))

    if recipes:
        proven = explored_all and not unfinished and not unsupported and scope_complete
        ranked = _assign(_dedupe(sorted(recipes, key=lambda item: item.key)), _TOP_K)
        alternatives, alternatives_done = _alternatives(bundle, request, budget, ranked, searches)
        return _feasible(
            bundle,
            request,
            ranked,
            alternatives,
            proven=proven,
            alternatives_done=alternatives_done,
            gaps=unsupported,
            scope_complete=scope_complete,
        )

    if unfinished or not explored_all:
        return _inconclusive()
    if not scope_complete:
        messages = ["The verified body list for this request is incomplete. " + _NOT_ILLEGAL]
        if unsupported:
            messages.extend(_merge_unsupported(unsupported).warnings)
        return _unsupported(tuple(dict.fromkeys(messages)), ("body_profiles",))
    if unsupported:
        return _merge_unsupported(unsupported)
    if pruned:
        return _closest(bundle, request, budget, pruned, profiles=_profiles_from(pruned))
    return _unsupported(
        ("No verified body was searched. " + _NOT_ILLEGAL,),
        ("body_profiles",),
    )


def _search_profile(
    bundle: RuleBundle,
    request: OptimizeRequest,
    profile: BodyProfile,
    budget: SolveBudget,
    *,
    relax_required: bool,
    penalize_excess: bool = True,
    cap: int = _PER_BODY_CAP,
) -> _BodySearch:
    locked = _lock_request(request, profile)
    prepared = _prepare(bundle, locked)
    if isinstance(prepared, Outcome):
        if prepared.status == "no_feasible_found_in_budget":
            kind: _Kind = "timeout"
            exhausted = False
        elif prepared.status == "infeasible_proven":
            kind = "pruned"
            exhausted = True
        else:
            kind = "unsupported"
            exhausted = True
        return _BodySearch(kind, profile, (), exhausted, prepared)

    found: list[Scored] = []
    excluded: list[dict[str, int]] = []
    proven_steps = True
    while len(found) < cap:
        if budget.expired():
            return _BodySearch("timeout", profile, tuple(found), False, None)
        hit = solve_exact(
            bundle,
            locked,
            prepared.space,
            spendable=prepared.spendable,
            max_time_seconds=budget.remaining(),
            reference_base=prepared.reference_base,
            reference_apps=prepared.reference_apps,
            excluded_bases=tuple(excluded),
            relax_required=relax_required,
            penalize_excess=penalize_excess,
        )
        if hit.classification is SolveClassification.infeasible:
            if found:
                return _BodySearch("recipes", profile, tuple(found), proven_steps, None)
            classified = _classify_infeasible(
                bundle,
                locked,
                prepared,
                SolveBudget(max(budget.remaining(), 0.001), budget.deadline),
            )
            kind = {
                "infeasible_proven": "pruned",
                "unsupported": "unsupported",
            }.get(classified.status, "timeout")
            exhausted = classified.status == "infeasible_proven"
            return _BodySearch(kind, profile, (), exhausted, classified)
        if hit.classification is SolveClassification.inconclusive or hit.candidate is None:
            return _BodySearch("timeout", profile, tuple(found), False, None)
        if hit.classification is not SolveClassification.proven:
            proven_steps = False
        check = validate_recipe(
            bundle,
            request,
            prepared.space.query,
            hit.candidate,
            enforce_requirements=not relax_required,
            preference_distance=_preference(request, profile),
        )
        if check.problems:
            logger.error("Validator rejected solver candidate: %s", "; ".join(check.problems))
            raise RuntimeError("Independent validation rejected the solver recipe.")
        physical = _physical_violations(request, profile)
        found.append(
            Scored(
                key=_rank_key(check, _stability(request, hit.candidate), profile.id, physical),
                fingerprint=_fingerprint(profile, hit.candidate),
                profile=profile,
                candidate=hit.candidate,
                check=check,
                physical_violations=physical,
            )
        )
        excluded.append(dict(hit.candidate.base))
        if not proven_steps:
            return _BodySearch("recipes", profile, tuple(found), False, None)
    return _BodySearch("recipes", profile, tuple(found), True, None)


def _feasible(
    bundle: RuleBundle,
    request: OptimizeRequest,
    ranked: list[Scored],
    alternatives: list[Recommendation],
    *,
    proven: bool,
    alternatives_done: bool,
    gaps: list[_BodySearch],
    scope_complete: bool,
) -> Outcome:
    recommendations = _recommendations(ranked)
    warnings = list(
        _success_warnings(
            proven=proven,
            synthetic=bundle.any_synthetic(),
            alternatives_done=alternatives_done,
            gaps=gaps,
        )
    )
    if not scope_complete:
        warnings.append(
            "The verified body list for this request is incomplete, "
            "so unlisted bodies were not searched."
        )
    if request.mode is SearchMode.refine:
        warnings.append(
            "The reference body was kept, and reference ratings were preferred "
            "after requested targets."
        )
    return Outcome(
        status="complete_proven" if proven else "partial_feasible",
        optimality_proven=proven,
        warnings=tuple(warnings),
        notes=(warnings[0],),
        missing_mechanics=(),
        conflicts=(),
        recommendation=recommendations[0],
        recommendations=tuple(recommendations),
        alternatives=tuple(alternatives),
    )


def _alternatives(
    bundle: RuleBundle,
    request: OptimizeRequest,
    budget: SolveBudget,
    ranked: list[Scored],
    searches: list[_BodySearch],
) -> tuple[list[Recommendation], bool]:
    if not ranked:
        return [], True
    best = ranked[0]
    best_short = _shortfall(request, best.candidate.final)
    collected: list[Scored] = []
    done = True
    profiles = [search.profile for search in searches if search.kind == "recipes"]
    for profile in profiles:
        if budget.expired():
            done = False
            break
        search = _search_profile(
            bundle,
            request,
            profile,
            budget,
            relax_required=False,
            penalize_excess=False,
            cap=_ALTERNATIVE_LIMIT,
        )
        if search.kind == "timeout" or not search.exhausted:
            done = False
        for recipe in search.recipes:
            if not _alternative_ok(request, best, best_short, recipe):
                continue
            collected.append(recipe)
    chosen = _dedupe(sorted(collected, key=lambda item: item.key))
    chosen = [item for item in chosen if item.fingerprint != best.fingerprint][:_ALTERNATIVE_LIMIT]
    top_ids = {item.fingerprint: index for index, item in enumerate(ranked, start=1)}
    cards: list[Recommendation] = []
    for index, recipe in enumerate(chosen, start=1):
        shared = top_ids.get(recipe.fingerprint)
        build_id = f"ephemeral-{shared}" if shared is not None else f"ephemeral-{_TOP_K + index}"
        card = _recommendation(recipe, index, build_id)
        if shared is not None:
            card = _annotate_overlap(card, shared)
        cards.append(card)
    return cards, done


def _alternative_ok(
    request: OptimizeRequest,
    best: Scored,
    best_short: tuple[int, int],
    recipe: Scored,
) -> bool:
    if recipe.check.required_violations:
        return False
    short = _shortfall(request, recipe.candidate.final)
    if short[0] > best_short[0] or short[1] > best_short[1]:
        return False
    if recipe.check.prioritized_unlock_misses > best.check.prioritized_unlock_misses:
        return False
    if recipe.check.normal_unlock_misses > best.check.normal_unlock_misses:
        return False
    if recipe.check.score + 1e-9 < best.check.score - ALTERNATIVE_SCORE_BAND:
        return False
    same_body = recipe.profile.tuple_key == best.profile.tuple_key
    same_base = recipe.candidate.base == best.candidate.base
    return not (same_body and same_base)


def _closest(
    bundle: RuleBundle,
    request: OptimizeRequest,
    budget: SolveBudget,
    pruned: list[_BodySearch],
    profiles: list[BodyProfile],
    conflicts: list[RequirementConflict] | None = None,
) -> Outcome:
    resolved = conflicts if conflicts is not None else _conflicts(pruned, profiles)
    if _allocation_conflict(resolved):
        return _infeasible(tuple(resolved))
    if budget.expired():
        return _infeasible_without_closest(resolved)
    bodies = profiles
    if not bodies:
        if request.mode is SearchMode.refine:
            return _infeasible(tuple(resolved))
        bodies = _nearest_legal_bodies(bundle, request)
    found: list[Scored] = []
    for profile in bodies:
        if budget.expired():
            break
        search = _search_profile(
            bundle,
            request,
            profile,
            budget,
            relax_required=True,
            cap=_PER_BODY_CAP,
        )
        found.extend(search.recipes)
    if not found:
        return _infeasible_without_closest(resolved)
    ranked = _assign(_dedupe(sorted(found, key=lambda item: item.key)), _TOP_K)
    best = ranked[0]
    if best.check.required_violations == 0 and best.physical_violations == 0:
        raise RuntimeError("Closest search found a recipe the exact search should have returned.")
    recommendations = _recommendations(ranked)
    unmet = (
        *_physical_unmet(request, best.profile),
        *_requirement_unmet(request, best),
    )
    warning = (
        "Verified rules prove the original request cannot be met. "
        "The listed builds relax the requirements in unmet_requirements. "
        "Game rules were not relaxed."
    )
    warnings = [warning, "Playstyle did not change this result."]
    if request.mode is SearchMode.refine:
        warnings.append("The reference body was kept.")
    if bundle.any_synthetic():
        warnings.append(
            "Synthetic rules produced this recipe. It is not an NBA 2K27 recommendation."
        )
    return Outcome(
        status="infeasible_proven",
        optimality_proven=True,
        warnings=tuple(warnings),
        notes=("The request contradicts verified rules. Closest builds are labeled.",),
        missing_mechanics=(),
        conflicts=tuple(resolved),
        recommendation=recommendations[0],
        recommendations=tuple(recommendations),
        unmet=tuple(unmet),
    )


def _infeasible_without_closest(conflicts: list[RequirementConflict]) -> Outcome:
    outcome = _infeasible(tuple(conflicts))
    warning = (
        "Verified rules prove this request cannot be met. "
        "A closest build was not found before the search budget ended."
    )
    return Outcome(
        status=outcome.status,
        optimality_proven=True,
        warnings=(warning,),
        notes=outcome.notes,
        missing_mechanics=(),
        conflicts=outcome.conflicts,
        recommendation=None,
    )


def _no_matching_body(
    bundle: RuleBundle,
    request: OptimizeRequest,
    budget: SolveBudget,
) -> Outcome:
    query = query_from_body(request.body)
    verified = _verified_profiles(bundle)
    if not verified:
        return _unsupported(
            ("No verified body profiles are loaded. This body was not judged legal or illegal.",),
            ("body_profiles",),
        )
    if not _scope_complete(bundle, query):
        return _unsupported(
            (
                "No verified body matches these locks, and the body list for that range "
                f"is incomplete. {_NOT_ILLEGAL}",
            ),
            ("body_profiles",),
        )
    conflict = _empty_conflict(bundle, query)
    if request.mode is SearchMode.refine or budget.expired():
        return _infeasible((conflict,))
    return _closest(bundle, request, budget, pruned=[], profiles=[], conflicts=[conflict])


def _nearest_legal_bodies(bundle: RuleBundle, request: OptimizeRequest) -> list[BodyProfile]:
    query = query_from_body(request.body)
    locked = [name for name, is_locked in _lock_flags(query).items() if is_locked]
    nearest: list[BodyProfile] = []
    for count in range(1, len(locked) + 1):
        found = False
        for dropped in itertools.combinations(locked, count):
            matched = _matching_profiles(bundle, request, dropped=set(dropped))
            if not matched:
                continue
            found = True
            nearest.extend(matched)
        if found:
            break
    unique: dict[tuple[object, ...], BodyProfile] = {}
    for profile in nearest:
        unique[profile.tuple_key] = profile
    return sorted(unique.values(), key=lambda profile: (_preference(request, profile), profile.id))


def _matching_profiles(
    bundle: RuleBundle,
    request: OptimizeRequest,
    dropped: set[str],
) -> list[BodyProfile]:
    if request.mode is SearchMode.refine and request.reference is not None and not dropped:
        return _refine_profiles(bundle, request)
    query = query_from_body(request.body)
    return [profile for profile in _verified_profiles(bundle) if _matches(profile, query, dropped)]


def _refine_profiles(bundle: RuleBundle, request: OptimizeRequest) -> list[BodyProfile]:
    reference = request.reference
    assert reference is not None
    key = (
        reference.body.build_type,
        reference.body.position,
        reference.body.height_in,
        reference.body.weight_lb,
        reference.body.wingspan_in,
    )
    return [profile for profile in _verified_profiles(bundle) if profile.tuple_key == key]


def _refine_block(request: OptimizeRequest) -> Outcome | None:
    if request.mode is not SearchMode.refine or request.reference is None:
        return None
    query = query_from_body(request.body)
    reference = request.reference.body
    mismatches = (
        (query.build_type_locked, query.build_type, reference.build_type),
        (query.position_locked, query.position, reference.position),
        (query.height_locked, query.height_in, reference.height_in),
        (query.weight_locked, query.weight_lb, reference.weight_lb),
        (query.wingspan_locked, query.wingspan_in, reference.wingspan_in),
    )
    if any(locked and value != expected for locked, value, expected in mismatches):
        return _unsupported(
            (
                "The reference body is not the locked body. Refine keeps the reference "
                "body, so other bodies were not searched.",
            ),
            ("body_profiles",),
        )
    return None


def _verified_profiles(bundle: RuleBundle) -> list[BodyProfile]:
    return [
        profile for profile in bundle.bodies.bodies if profile.status is VerificationStatus.verified
    ]


def _matches(profile: BodyProfile, query: BodyQuery, dropped: set[str]) -> bool:
    checks = (
        ("build_type", query.build_type_locked, profile.build_type, query.build_type),
        ("position", query.position_locked, profile.position, query.position),
        ("height_in", query.height_locked, profile.height_in, query.height_in),
        ("weight_lb", query.weight_locked, profile.weight_lb, query.weight_lb),
        ("wingspan_in", query.wingspan_locked, profile.wingspan_in, query.wingspan_in),
    )
    for name, locked, actual, expected in checks:
        if name in dropped or not locked or expected is None:
            continue
        if actual != expected:
            return False
    return True


def _scope_complete(bundle: RuleBundle, query: BodyQuery) -> bool:
    build_types = (
        [query.build_type]
        if query.build_type_locked and query.build_type is not None
        else list(BuildType)
    )
    positions = (
        [query.position] if query.position_locked and query.position is not None else list(Position)
    )
    for build_type in build_types:
        for position in positions:
            entry = bundle.coverage_entry(build_type, position)
            if entry is None or entry.enumeration != "complete":
                return False
    return True


def _lock_flags(query: BodyQuery) -> dict[str, bool]:
    return {
        "build_type": query.build_type_locked,
        "position": query.position_locked,
        "height_in": query.height_locked,
        "weight_lb": query.weight_locked,
        "wingspan_in": query.wingspan_locked,
    }


def _empty_conflict(bundle: RuleBundle, query: BodyQuery) -> RequirementConflict:
    if query.fully_locked():
        finding = assess_body(bundle, query)
        return RequirementConflict(field="body", message=finding.message)
    return RequirementConflict(
        field="body",
        message="No verified body matches the locked measurements.",
    )


def _lock_request(request: OptimizeRequest, profile: BodyProfile) -> OptimizeRequest:
    return request.model_copy(
        update={
            "body": BodyInput(
                build_type=LockedBuildType(value=profile.build_type, locked=True),
                position=LockedPosition(value=profile.position, locked=True),
                height_in=LockedInches(value=profile.height_in, locked=True),
                weight_lb=LockedPounds(value=profile.weight_lb, locked=True),
                wingspan_in=LockedInches(value=profile.wingspan_in, locked=True),
            )
        }
    )


def _preference(request: OptimizeRequest, profile: BodyProfile) -> int:
    query = query_from_body(request.body)
    distance = 0
    if query.build_type is not None and profile.build_type is not query.build_type:
        distance += 1000
    if query.position is not None and profile.position is not query.position:
        distance += 1000
    if query.height_in is not None:
        distance += abs(profile.height_in - query.height_in)
    if query.weight_lb is not None:
        distance += abs(profile.weight_lb - query.weight_lb)
    if query.wingspan_in is not None:
        distance += abs(profile.wingspan_in - query.wingspan_in)
    return distance


def _physical_violations(request: OptimizeRequest, profile: BodyProfile) -> int:
    query = query_from_body(request.body)
    violations = (
        (query.build_type_locked, profile.build_type, query.build_type),
        (query.position_locked, profile.position, query.position),
        (query.height_locked, profile.height_in, query.height_in),
        (query.weight_locked, profile.weight_lb, query.weight_lb),
        (query.wingspan_locked, profile.wingspan_in, query.wingspan_in),
    )
    return sum(1 for locked, actual, expected in violations if locked and actual != expected)


def _stability(request: OptimizeRequest, candidate: Candidate) -> int:
    if request.mode is not SearchMode.refine or request.reference is None:
        return 0
    ratings = {item.id: item.rating for item in request.reference.base_attributes}
    reference_apps = dict.fromkeys(candidate.base, 0)
    for allocation in request.reference.cap_breaker_allocations:
        if allocation.attribute_id in reference_apps:
            reference_apps[allocation.attribute_id] += allocation.applications
    spent = dict.fromkeys(candidate.base, 0)
    for allocation in candidate.allocations:
        spent[allocation.attribute_id] += allocation.applications
    base_gap = sum(abs(candidate.base[attr] - ratings.get(attr, 0)) for attr in candidate.base)
    app_gap = sum(abs(spent[attr] - reference_apps[attr]) for attr in candidate.base)
    return base_gap + app_gap


def _rank_key(
    check: RecipeCheck,
    stability: int,
    profile_id: str,
    physical: int,
) -> tuple[int, ...]:
    return (
        check.required_violations,
        check.required_severity,
        physical,
        check.prioritized_points + check.prioritized_unlock_misses,
        check.normal_points,
        check.normal_unlock_misses,
        check.preference_distance,
        stability,
        check.applications_used,
        _id_key(profile_id),
    )


def _id_key(profile_id: str) -> int:
    return sum(profile_id.encode("utf-8"))


def _fingerprint(profile: BodyProfile, candidate: Candidate) -> tuple[object, ...]:
    base = tuple(sorted(candidate.base.items()))
    allocations = tuple(
        (item.pool_id, item.attribute_id, item.applications, item.rating_gain)
        for item in candidate.allocations
    )
    return (profile.tuple_key, base, allocations, candidate.name)


def _shortfall(request: OptimizeRequest, final: dict[str, int]) -> tuple[int, int]:
    prioritized = 0
    normal = 0
    for target in request.attribute_targets:
        if target.importance is Importance.required:
            continue
        gap = max(0, target.target - final[target.id])
        if target.importance is Importance.prioritized:
            prioritized += gap
        else:
            normal += gap
    return prioritized, normal


def _dedupe(recipes: list[Scored]) -> list[Scored]:
    seen: set[tuple[object, ...]] = set()
    unique: list[Scored] = []
    for recipe in recipes:
        if recipe.fingerprint in seen:
            continue
        seen.add(recipe.fingerprint)
        unique.append(recipe)
    return unique


def _assign(recipes: list[Scored], limit: int) -> list[Scored]:
    return recipes[:limit]


def _recommendations(recipes: list[Scored]) -> list[Recommendation]:
    return [
        _recommendation(recipe, index, f"ephemeral-{index}")
        for index, recipe in enumerate(recipes, start=1)
    ]


def _recommendation(recipe: Scored, rank: int, build_id: str) -> Recommendation:
    build_type, position, height_in, weight_lb, wingspan_in = recipe.profile.tuple_key
    return Recommendation(
        build_id=build_id,
        name=recipe.candidate.name,
        rank=rank,
        score=recipe.check.score,
        body=BuildMeasurements(
            build_type=build_type,
            position=position,
            height_in=height_in,
            weight_lb=weight_lb,
            wingspan_in=wingspan_in,
        ),
        base_attributes=_ratings(list(recipe.candidate.base), recipe.candidate.base),
        final_attributes=_ratings(list(recipe.candidate.final), recipe.candidate.final),
        cap_breaker_allocations=[
            CapBreakerAllocation(
                pool_id=item.pool_id,
                attribute_id=item.attribute_id,
                applications=item.applications,
                rating_gain=item.rating_gain,
            )
            for item in recipe.candidate.allocations
        ],
        eligible_badges=list(recipe.check.badges),
        eligible_animations=list(recipe.check.animations),
        eligible_takeovers=list(recipe.check.takeovers),
        score_breakdown=ScoreBreakdown(
            scoring_version=SCORING_VERSION,
            components=list(recipe.check.components),
        ),
        deviations=list(recipe.check.deviations),
        verification="verified",
    )


def _annotate_overlap(card: Recommendation, top_rank: int) -> Recommendation:
    note = ScoreComponent(
        id="alternative_overlap",
        weight=0,
        value=float(top_rank),
        note=f"Same build as top rank {top_rank}.",
    )
    components = [*card.score_breakdown.components, note]
    return card.model_copy(
        update={
            "score_breakdown": card.score_breakdown.model_copy(update={"components": components})
        }
    )


def _success_warnings(
    *,
    proven: bool,
    synthetic: bool,
    alternatives_done: bool,
    gaps: list[_BodySearch],
) -> tuple[str, ...]:
    if proven:
        lead = "Optimum is proven for the verified bodies that match this request."
    else:
        lead = (
            "Validated builds were found. The search ended before every matching "
            "body was certified, so this is not a proven top 5."
        )
    warnings = [lead, "Playstyle did not change this result."]
    if gaps:
        names = ", ".join(search.profile.id for search in gaps)
        warnings.append(
            f"{names} could not be certified, so those bodies were not ranked. {_NOT_ILLEGAL}"
        )
    if not alternatives_done:
        warnings.append("The distinct-alternative search ended early, so that list may be short.")
    if synthetic:
        warnings.append(
            "Synthetic rules produced this recipe. It is not an NBA 2K27 recommendation."
        )
    return tuple(warnings)


def _conflicts(pruned: list[_BodySearch], profiles: list[BodyProfile]) -> list[RequirementConflict]:
    conflicts: list[RequirementConflict] = []
    prefix = len(profiles) > 1
    for search in pruned:
        if search.outcome is None:
            continue
        for conflict in search.outcome.conflicts:
            message = conflict.message
            if prefix:
                message = f"On {search.profile.id}, {message}"
            conflicts.append(RequirementConflict(field=conflict.field, message=message))
    if conflicts:
        return conflicts
    return [
        RequirementConflict(
            field="attribute_targets",
            message="The required ratings and unlocks contradict the verified bodies.",
        )
    ]


def _allocation_conflict(conflicts: list[RequirementConflict]) -> bool:
    return any("forbidden" in conflict.message for conflict in conflicts)


def _profiles_from(searches: list[_BodySearch]) -> list[BodyProfile]:
    return [search.profile for search in searches]


def _merge_unsupported(searches: list[_BodySearch]) -> Outcome:
    messages: list[str] = []
    mechanics: list[str] = []
    for search in searches:
        if search.outcome is None:
            continue
        messages.extend(search.outcome.warnings)
        mechanics.extend(search.outcome.missing_mechanics)
    if not messages:
        messages.append(f"A matching body could not be certified. {_NOT_ILLEGAL}")
    return _unsupported(tuple(dict.fromkeys(messages)), tuple(mechanics or ("body_profiles",)))


def _physical_unmet(request: OptimizeRequest, profile: BodyProfile) -> list[UnmetRequirement]:
    query = query_from_body(request.body)
    rows = (
        (
            "body.build_type",
            "Build type",
            query.build_type_locked,
            query.build_type,
            profile.build_type,
        ),
        ("body.position", "Position", query.position_locked, query.position, profile.position),
        ("body.height_in", "Height", query.height_locked, query.height_in, profile.height_in),
        ("body.weight_lb", "Weight", query.weight_locked, query.weight_lb, profile.weight_lb),
        (
            "body.wingspan_in",
            "Wingspan",
            query.wingspan_locked,
            query.wingspan_in,
            profile.wingspan_in,
        ),
    )
    unmet: list[UnmetRequirement] = []
    for field, label, locked, requested, achieved in rows:
        if not locked or requested == achieved or requested is None:
            continue
        shown = achieved.value if isinstance(achieved, (BuildType, Position)) else achieved
        unmet.append(
            UnmetRequirement(
                field=field,
                requested=str(requested),
                achieved=str(shown),
                message=(
                    f"{label} was locked at {requested}. The closest verified body uses {achieved}."
                ),
            )
        )
    return unmet


def _requirement_unmet(request: OptimizeRequest, recipe: Scored) -> list[UnmetRequirement]:
    required = {
        target.id: target.target
        for target in request.attribute_targets
        if target.importance is Importance.required
    }
    unmet = [
        UnmetRequirement(
            field=f"attribute_targets.{note.attribute_id}",
            requested=str(note.requested),
            achieved=str(note.achieved),
            message=note.message,
        )
        for note in recipe.check.deviations
        if note.attribute_id in required
    ]
    eligible = {item.id: item.highest_tier for item in recipe.check.badges}
    for badge in request.badges:
        if badge.importance is not Importance.required:
            continue
        tier = eligible.get(badge.id)
        met = tier is not None and _TIER_RANK[tier.value] >= _TIER_RANK[badge.minimum_tier.value]
        if met:
            continue
        unmet.append(
            UnmetRequirement(
                field=f"badges.{badge.id}",
                requested=badge.minimum_tier.value,
                achieved=tier.value if tier is not None else "none",
                message=(
                    f"Badge {badge.id} was required at {badge.minimum_tier.value}. "
                    "The closest verified recipe does not meet that tier."
                ),
            )
        )
    return unmet
