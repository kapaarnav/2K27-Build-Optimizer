"""CP-SAT model for one locked body.

Base ratings are chosen from verified overall-and-name rows. Cap Breaker
results come from verified gain steps. Linked-attribute rules are constraints,
not a post-pass. A required final rating or required unlock is hard. Prioritized
and normal requests are penalties.
"""

from dataclasses import dataclass
from enum import StrEnum

from ortools.sat.python import cp_model

from app.domain import BadgeTier, Importance, PoolKind, VerificationStatus
from app.optimizer.scoring import ObjectiveWeights, objective_weights
from app.optimizer.validator import Allocation, Candidate
from app.rules.engine import BodyQuery
from app.rules.models import BadgeRule, BodyProfile, EligibilityRule, GainStep, LinkRule, RuleBundle
from app.schemas.optimize import OptimizeRequest

_TIER_RANK = {
    BadgeTier.bronze: 0,
    BadgeTier.silver: 1,
    BadgeTier.gold: 2,
    BadgeTier.hall_of_fame: 3,
}


class SolveClassification(StrEnum):
    proven = "proven"
    feasible = "feasible"
    infeasible = "infeasible"
    inconclusive = "inconclusive"


@dataclass(frozen=True)
class VerifiedVector:
    base: dict[str, int]
    overall: int
    name: str


@dataclass(frozen=True)
class SearchSpace:
    query: BodyQuery
    profile: BodyProfile
    attribute_ids: list[str]
    bounds: dict[str, tuple[int, int]]
    vectors: list[VerifiedVector]
    gains: list[GainStep]
    permissions: frozenset[tuple[str, str]]
    application_limit: int | None


@dataclass(frozen=True)
class ModelHit:
    classification: SolveClassification
    candidate: Candidate | None


class _Names:
    def __init__(self) -> None:
        self._n = 0

    def __call__(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}_{self._n}"


def classify_cp_status(status: int, has_solution: bool) -> SolveClassification:
    if status == cp_model.MODEL_INVALID:
        raise RuntimeError("The single-body model is invalid.")
    if has_solution and status == cp_model.OPTIMAL:
        return SolveClassification.proven
    if has_solution and status == cp_model.FEASIBLE:
        return SolveClassification.feasible
    if status == cp_model.INFEASIBLE:
        return SolveClassification.infeasible
    return SolveClassification.inconclusive


def solve_exact(
    bundle: RuleBundle,
    request: OptimizeRequest,
    space: SearchSpace,
    *,
    spendable: int,
    max_time_seconds: float,
    reference_base: dict[str, int] | None,
    reference_apps: dict[str, int] | None,
) -> ModelHit:
    model = cp_model.CpModel()
    names = _Names()
    attrs = space.attribute_ids
    steps = _usable_steps(space, spendable)
    app_upper = _application_upper(request, space, steps)
    bases = {
        attr: model.NewIntVar(space.bounds[attr][0], space.bounds[attr][1], names("base"))
        for attr in attrs
    }
    finals = {
        attr: model.NewIntVar(*_final_domain(attr, space, steps, request), names("final"))
        for attr in attrs
    }
    apps = {attr: model.NewIntVar(0, app_upper[attr], names("apps")) for attr in attrs}
    _choose_base_row(model, names, space, bases)
    _choose_gains(model, names, attrs, steps, bases, finals, apps, app_upper)
    _add_link_closure(model, names, bases, space.bounds, bundle.links.links)
    used = _add_pools(model, names, request, space, apps, spendable)
    _add_targets_and_unlocks(
        model,
        names,
        bundle,
        request,
        space,
        bases,
        finals,
        apps,
        used,
        app_upper,
        reference_base,
        reference_apps,
    )
    return _read_hit(
        model,
        space,
        request,
        attrs,
        max_time_seconds,
        bases,
        finals,
        apps,
        used,
    )


def relaxation_status(
    bundle: RuleBundle,
    request: OptimizeRequest,
    space: SearchSpace,
    *,
    can_raise: set[str],
    max_time_seconds: float,
) -> SolveClassification:
    """Outer model used only to decide whether a miss is proven.

    Bases stay inside verified bounds and obey the link closure. Finals may
    rise when the request can spend a breaker, and they cannot fall: the loader
    accepts only non-negative gains. Verified cost rows are not required here.
    """

    model = cp_model.CpModel()
    names = _Names()
    attrs = space.attribute_ids
    bases = {
        attr: model.NewIntVar(space.bounds[attr][0], space.bounds[attr][1], names("base"))
        for attr in attrs
    }
    finals = {attr: model.NewIntVar(0, 150, names("final")) for attr in attrs}
    for attr in attrs:
        if attr in can_raise:
            model.Add(finals[attr] >= bases[attr])
        else:
            model.Add(finals[attr] == bases[attr])
    _add_link_closure(model, names, bases, space.bounds, bundle.links.links)
    for target in request.attribute_targets:
        if target.importance is Importance.required:
            model.Add(finals[target.id] == target.target)
    for badge in request.badges:
        if badge.importance is not Importance.required:
            continue
        rules = _covering(bundle.eligibility.badges, badge.id, space)
        _require_unlock(model, names, rules, bases, finals, badge.minimum_tier)
    for animation in request.animations:
        if animation.importance is not Importance.required:
            continue
        rules = _covering(bundle.eligibility.animations, animation.id, space)
        _require_unlock(model, names, rules, bases, finals, None)
    for takeover in request.takeovers:
        if takeover.importance is not Importance.required:
            continue
        rules = _covering(bundle.eligibility.takeovers, takeover.id, space)
        _require_unlock(model, names, rules, bases, finals, None)
    solver = _solver(max_time_seconds)
    status = solver.Solve(model)
    has_solution = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    return classify_cp_status(status, has_solution)


def _solver(max_time_seconds: float) -> cp_model.CpSolver:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(max_time_seconds, 0.001)
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 1
    solver.parameters.log_search_progress = False
    return solver


def _usable_steps(space: SearchSpace, spendable: int) -> list[GainStep]:
    usable: list[GainStep] = []
    for step in space.gains:
        if step.status is not VerificationStatus.verified:
            continue
        lower, upper = space.bounds[step.attribute_id]
        if step.starting_rating < lower or step.starting_rating > upper:
            continue
        if step.applications > spendable:
            continue
        if space.application_limit is not None and step.applications > space.application_limit:
            continue
        usable.append(step)
    return usable


def _application_upper(
    request: OptimizeRequest,
    space: SearchSpace,
    steps: list[GainStep],
) -> dict[str, int]:
    forbidden = set(request.cap_breakers.forbidden_attribute_ids)
    minimums = {item.attribute_id: item.count for item in request.cap_breakers.minimum_allocations}
    upper: dict[str, int] = {}
    for attr in space.attribute_ids:
        if attr in forbidden:
            upper[attr] = 0
            continue
        height = max(
            (step.applications for step in steps if step.attribute_id == attr),
            default=0,
        )
        upper[attr] = max(height, minimums.get(attr, 0))
    return upper


def _final_domain(
    attribute_id: str,
    space: SearchSpace,
    steps: list[GainStep],
    request: OptimizeRequest,
) -> tuple[int, int]:
    lower, upper = space.bounds[attribute_id]
    for step in steps:
        if step.attribute_id != attribute_id:
            continue
        value = step.starting_rating + step.rating_gain
        lower = min(lower, value)
        upper = max(upper, value)
    for target in request.attribute_targets:
        if target.id == attribute_id:
            lower = min(lower, target.target)
            upper = max(upper, target.target)
    return lower, upper


def _choose_base_row(
    model: cp_model.CpModel,
    names: _Names,
    space: SearchSpace,
    bases: dict[str, cp_model.IntVar],
) -> None:
    row = model.NewIntVar(0, len(space.vectors) - 1, names("row"))
    for attr in space.attribute_ids:
        model.AddElement(row, [vector.base[attr] for vector in space.vectors], bases[attr])


def _choose_gains(
    model: cp_model.CpModel,
    names: _Names,
    attrs: list[str],
    steps: list[GainStep],
    bases: dict[str, cp_model.IntVar],
    finals: dict[str, cp_model.IntVar],
    apps: dict[str, cp_model.IntVar],
    app_upper: dict[str, int],
) -> None:
    for attr in attrs:
        options = []
        zero = model.NewBoolVar(names("zero"))
        model.Add(apps[attr] == 0).OnlyEnforceIf(zero)
        model.Add(finals[attr] == bases[attr]).OnlyEnforceIf(zero)
        options.append(zero)
        for step in steps:
            if step.attribute_id != attr or step.applications > app_upper[attr]:
                continue
            chosen = model.NewBoolVar(names("step"))
            model.Add(bases[attr] == step.starting_rating).OnlyEnforceIf(chosen)
            model.Add(apps[attr] == step.applications).OnlyEnforceIf(chosen)
            model.Add(finals[attr] == step.starting_rating + step.rating_gain).OnlyEnforceIf(chosen)
            options.append(chosen)
        model.AddExactlyOne(options)


def _add_link_closure(
    model: cp_model.CpModel,
    names: _Names,
    bases: dict[str, cp_model.IntVar],
    bounds: dict[str, tuple[int, int]],
    links: list[LinkRule],
) -> None:
    for link in links:
        if link.status is not VerificationStatus.verified:
            continue
        if link.source_attribute_id not in bases or link.target_attribute_id not in bases:
            continue
        lower, upper = bounds[link.source_attribute_id]
        if link.when_source_at_least <= lower:
            model.Add(bases[link.target_attribute_id] >= link.target_minimum)
            continue
        if link.when_source_at_least > upper:
            continue
        triggered = model.NewBoolVar(names("link"))
        source = bases[link.source_attribute_id]
        model.Add(source >= link.when_source_at_least).OnlyEnforceIf(triggered)
        model.Add(source <= link.when_source_at_least - 1).OnlyEnforceIf(triggered.Not())
        model.Add(bases[link.target_attribute_id] >= link.target_minimum).OnlyEnforceIf(triggered)


def _add_pools(
    model: cp_model.CpModel,
    names: _Names,
    request: OptimizeRequest,
    space: SearchSpace,
    apps: dict[str, cp_model.IntVar],
    spendable: int,
) -> dict[tuple[str, str], cp_model.IntVar]:
    forbidden = set(request.cap_breakers.forbidden_attribute_ids)
    used: dict[tuple[str, str], cp_model.IntVar] = {}
    pools = request.cap_breakers.pools
    for pool in pools:
        for attr in space.attribute_ids:
            var = model.NewIntVar(0, pool.available, names("used"))
            used[pool.id, attr] = var
            if not _pool_allows(pool.kind, pool.category, attr, forbidden, space.permissions):
                model.Add(var == 0)
    for attr in space.attribute_ids:
        if pools:
            model.Add(sum(used[pool.id, attr] for pool in pools) == apps[attr])
        else:
            model.Add(apps[attr] == 0)
    for pool in pools:
        model.Add(sum(used[pool.id, attr] for attr in space.attribute_ids) <= pool.available)
    if pools:
        model.Add(sum(used.values()) <= spendable)
    return used


def _pool_allows(
    kind: PoolKind,
    category: str | None,
    attribute_id: str,
    forbidden: set[str],
    permissions: frozenset[tuple[str, str]],
) -> bool:
    if attribute_id in forbidden:
        return False
    if kind is PoolKind.unrestricted:
        return True
    return (category or "", attribute_id) in permissions


def _add_targets_and_unlocks(
    model: cp_model.CpModel,
    names: _Names,
    bundle: RuleBundle,
    request: OptimizeRequest,
    space: SearchSpace,
    bases: dict[str, cp_model.IntVar],
    finals: dict[str, cp_model.IntVar],
    apps: dict[str, cp_model.IntVar],
    used: dict[tuple[str, str], cp_model.IntVar],
    app_upper: dict[str, int],
    reference_base: dict[str, int] | None,
    reference_apps: dict[str, int] | None,
) -> None:
    terms: list[cp_model.LinearExpr] = []
    minimums = {item.attribute_id: item.count for item in request.cap_breakers.minimum_allocations}
    for attr, count in minimums.items():
        if count > 0:
            model.Add(apps[attr] >= count)
    for target in request.attribute_targets:
        if target.importance is Importance.required:
            model.Add(finals[target.id] == target.target)

    n_unlocks = len(request.badges) + len(request.animations) + len(request.takeovers)
    weights = objective_weights(
        n_attributes=len(space.attribute_ids),
        n_pools=len(request.cap_breakers.pools),
        total_applications=sum(app_upper.values()),
        n_unlocks=n_unlocks,
    )
    for target in request.attribute_targets:
        if target.importance is Importance.required:
            continue
        deviation = model.NewIntVar(0, 150, names("deviation"))
        model.AddAbsEquality(deviation, finals[target.id] - target.target)
        weight = (
            weights.prioritized if target.importance is Importance.prioritized else weights.normal
        )
        terms.append(deviation * weight)

    _penalize_unlocks(model, names, bundle, request, space, bases, finals, weights, terms)
    if reference_base is not None and reference_apps is not None:
        for attr in space.attribute_ids:
            base_gap = model.NewIntVar(0, 150, names("reference_base"))
            model.AddAbsEquality(base_gap, bases[attr] - reference_base[attr])
            terms.append(base_gap * weights.stability)
            app_span = max(app_upper[attr], reference_apps.get(attr, 0))
            app_gap = model.NewIntVar(0, app_span, names("reference_apps"))
            model.AddAbsEquality(app_gap, apps[attr] - reference_apps.get(attr, 0))
            terms.append(app_gap * weights.stability)
    for index, pool in enumerate(request.cap_breakers.pools):
        for attr in space.attribute_ids:
            terms.append(used[pool.id, attr] * (weights.breaker_base + index))
    if not terms:
        model.Minimize(0)
        return
    total = terms[0]
    for term in terms[1:]:
        total += term
    model.Minimize(total)


def _penalize_unlocks(
    model: cp_model.CpModel,
    names: _Names,
    bundle: RuleBundle,
    request: OptimizeRequest,
    space: SearchSpace,
    bases: dict[str, cp_model.IntVar],
    finals: dict[str, cp_model.IntVar],
    weights: ObjectiveWeights,
    terms: list[cp_model.LinearExpr],
) -> None:
    for badge in request.badges:
        rules = _covering(bundle.eligibility.badges, badge.id, space)
        _one_unlock(
            model,
            names,
            rules,
            bases,
            finals,
            badge.minimum_tier,
            badge.importance,
            weights,
            terms,
        )
    for animation in request.animations:
        rules = _covering(bundle.eligibility.animations, animation.id, space)
        _one_unlock(model, names, rules, bases, finals, None, animation.importance, weights, terms)
    for takeover in request.takeovers:
        rules = _covering(bundle.eligibility.takeovers, takeover.id, space)
        _one_unlock(model, names, rules, bases, finals, None, takeover.importance, weights, terms)


def _one_unlock(
    model: cp_model.CpModel,
    names: _Names,
    rules: list[EligibilityRule],
    bases: dict[str, cp_model.IntVar],
    finals: dict[str, cp_model.IntVar],
    minimum_tier: BadgeTier | None,
    importance: Importance,
    weights: ObjectiveWeights,
    terms: list[cp_model.LinearExpr],
) -> None:
    if importance is Importance.required:
        _require_unlock(model, names, rules, bases, finals, minimum_tier)
        return
    choices = _unlock_choices(model, names, rules, bases, finals, minimum_tier)
    missed = model.NewBoolVar(names("miss"))
    if choices:
        model.AddBoolOr([*choices, missed])
        for choice in choices:
            model.AddImplication(choice, missed.Not())
    else:
        model.Add(missed == 1)
    weight = weights.prioritized if importance is Importance.prioritized else weights.unlock_normal
    terms.append(missed * weight)


def _require_unlock(
    model: cp_model.CpModel,
    names: _Names,
    rules: list[EligibilityRule],
    bases: dict[str, cp_model.IntVar],
    finals: dict[str, cp_model.IntVar],
    minimum_tier: BadgeTier | None,
) -> None:
    choices = _unlock_choices(model, names, rules, bases, finals, minimum_tier)
    if not choices:
        raise RuntimeError("A required unlock has no verified predicate in the model.")
    model.AddBoolOr(choices)


def _unlock_choices(
    model: cp_model.CpModel,
    names: _Names,
    rules: list[EligibilityRule],
    bases: dict[str, cp_model.IntVar],
    finals: dict[str, cp_model.IntVar],
    minimum_tier: BadgeTier | None,
) -> list[cp_model.IntVar]:
    choices: list[cp_model.IntVar] = []
    for rule in rules:
        if minimum_tier is not None and (
            not isinstance(rule, BadgeRule) or _TIER_RANK[rule.tier] < _TIER_RANK[minimum_tier]
        ):
            continue
        ratings = bases if rule.applies_to == "base" else finals
        chosen = model.NewBoolVar(names("unlock"))
        for requirement in rule.requirements:
            model.Add(ratings[requirement.attribute_id] >= requirement.minimum).OnlyEnforceIf(
                chosen
            )
        choices.append(chosen)
    return choices


def _covering(
    rules: list[EligibilityRule],
    unlock_id: str,
    space: SearchSpace,
) -> list[EligibilityRule]:
    return [
        rule
        for rule in rules
        if rule.id == unlock_id
        and rule.status is VerificationStatus.verified
        and rule.covers_body(space.query.key())
    ]


def _read_hit(
    model: cp_model.CpModel,
    space: SearchSpace,
    request: OptimizeRequest,
    attrs: list[str],
    max_time_seconds: float,
    bases: dict[str, cp_model.IntVar],
    finals: dict[str, cp_model.IntVar],
    apps: dict[str, cp_model.IntVar],
    used: dict[tuple[str, str], cp_model.IntVar],
) -> ModelHit:
    solver = _solver(max_time_seconds)
    status = solver.Solve(model)
    has_solution = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    classification = classify_cp_status(status, has_solution)
    if not has_solution:
        return ModelHit(classification, None)
    solved_base = {attr: solver.Value(bases[attr]) for attr in attrs}
    vector = next(item for item in space.vectors if item.base == solved_base)
    solved_apps = {attr: solver.Value(apps[attr]) for attr in attrs}
    gains = {
        attr: _gain_amount(space, attr, solved_base[attr], solved_apps[attr]) for attr in attrs
    }
    remaining = dict(gains)
    rows: list[Allocation] = []
    for pool in request.cap_breakers.pools:
        for attr in attrs:
            count = solver.Value(used[pool.id, attr])
            if count <= 0:
                continue
            rows.append(
                Allocation(
                    pool_id=pool.id,
                    attribute_id=attr,
                    applications=count,
                    rating_gain=remaining.pop(attr, 0),
                )
            )
    if any(amount > 0 for amount in remaining.values()):
        raise RuntimeError("Cap Breaker applications were not assigned to a pool.")
    candidate = Candidate(
        base=solved_base,
        final={attr: solver.Value(finals[attr]) for attr in attrs},
        allocations=tuple(rows),
        name=vector.name,
        overall=vector.overall,
    )
    return ModelHit(classification, candidate)


def _gain_amount(space: SearchSpace, attribute_id: str, starting: int, applications: int) -> int:
    if applications == 0:
        return 0
    for step in space.gains:
        if (
            step.attribute_id == attribute_id
            and step.starting_rating == starting
            and step.applications == applications
            and step.status is VerificationStatus.verified
        ):
            return step.rating_gain
    raise RuntimeError("Solved applications have no verified gain step.")
