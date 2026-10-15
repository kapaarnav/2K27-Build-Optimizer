import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from ortools.sat.python import cp_model

from app.domain import BadgeTier
from app.optimizer.cpsat import SolveClassification, classify_cp_status
from app.optimizer.solve import SolveBudget, solve_locked_body
from app.optimizer.validator import Allocation, Candidate, validate_recipe
from app.rules.engine import query_from_body
from app.rules.loader import load_ruleset
from app.schemas.optimize import OptimizeRequest
from app.services.planning import plan_optimize

_GUARD = Path(__file__).parent / "fixtures" / "synthetic" / "guard"


def _locked_body(
    position: str = "PG",
    height: int = 70,
    weight: int = 170,
    wingspan: int = 70,
) -> dict[str, object]:
    return {
        "build_type": {"value": "male", "locked": True},
        "position": {"value": position, "locked": True},
        "height_in": {"value": height, "locked": True},
        "weight_lb": {"value": weight, "locked": True},
        "wingspan_in": {"value": wingspan, "locked": True},
    }


def _request(targets: list[dict[str, object]], **extra: object) -> OptimizeRequest:
    payload: dict[str, object] = {
        "body": extra.pop("body", _locked_body()),
        "attribute_targets": targets,
    }
    payload.update(extra)
    return OptimizeRequest.model_validate(payload)


def _pair(attribute_id: str, target: int, importance: str = "required") -> dict[str, object]:
    return {"id": attribute_id, "target": target, "importance": importance}


def _text(outcome) -> str:
    parts = list(outcome.warnings)
    parts.extend(conflict.message for conflict in outcome.conflicts)
    return " ".join(parts).lower()


def test_locked_pg_round_trip_emits_a_complete_recipe() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = solve_locked_body(
        ruleset.bundle,
        _request(
            [_pair("toy_shot", 80), _pair("toy_finish", 40)],
            cap_breakers={"pools": [{"id": "general", "kind": "unrestricted", "available": 5}]},
            badges=[{"id": "toy_badge", "minimum_tier": "gold", "importance": "required"}],
            animations=[{"id": "toy_anim", "importance": "required"}],
            takeovers=[{"id": "toy_takeover", "importance": "required"}],
        ),
    )
    assert outcome.status == "complete_proven"
    assert outcome.optimality_proven is True
    recipe = outcome.recommendation
    assert recipe is not None
    assert recipe.name == "TOY_ARCHETYPE"
    assert recipe.verification == "verified"
    assert recipe.score == 100
    assert [(item.id, item.rating) for item in recipe.base_attributes] == [
        ("toy_shot", 80),
        ("toy_finish", 40),
    ]
    assert [(item.id, item.rating) for item in recipe.final_attributes] == [
        ("toy_shot", 80),
        ("toy_finish", 40),
    ]
    assert recipe.cap_breaker_allocations == []
    assert recipe.eligible_badges[0].id == "toy_badge"
    assert recipe.eligible_badges[0].highest_tier is BadgeTier.gold
    assert [item.id for item in recipe.eligible_animations] == ["toy_anim"]
    assert [item.id for item in recipe.eligible_takeovers] == ["toy_takeover"]
    overall = next(
        item for item in recipe.score_breakdown.components if item.id == "observed_overall"
    )
    assert overall.value == 70
    assert recipe.deviations == []
    assert "not an nba 2k27 recommendation" in _text(outcome)


def test_verified_breaker_step_is_used_when_the_final_requires_it() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = solve_locked_body(
        ruleset.bundle,
        _request(
            [_pair("toy_shot", 82), _pair("toy_finish", 40)],
            cap_breakers={"pools": [{"id": "general", "kind": "unrestricted", "available": 1}]},
        ),
    )
    recipe = outcome.recommendation
    assert outcome.status == "complete_proven"
    assert recipe is not None
    assert recipe.name == "TOY_ARCHETYPE"
    assert [(item.id, item.rating) for item in recipe.base_attributes] == [
        ("toy_shot", 80),
        ("toy_finish", 40),
    ]
    assert [(item.id, item.rating) for item in recipe.final_attributes] == [
        ("toy_shot", 82),
        ("toy_finish", 40),
    ]
    assert len(recipe.cap_breaker_allocations) == 1
    allocation = recipe.cap_breaker_allocations[0]
    assert allocation.pool_id == "general"
    assert allocation.attribute_id == "toy_shot"
    assert allocation.applications == 1
    assert allocation.rating_gain == 2


def test_specialization_pool_spends_only_on_a_verified_permission() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = solve_locked_body(
        ruleset.bundle,
        _request(
            [_pair("toy_shot", 82), _pair("toy_finish", 40)],
            cap_breakers={
                "pools": [
                    {
                        "id": "spec_shot",
                        "kind": "specialization",
                        "category": "toy_shooting",
                        "available": 1,
                    }
                ]
            },
        ),
    )
    recipe = outcome.recommendation
    assert outcome.status == "complete_proven"
    assert recipe is not None
    assert recipe.cap_breaker_allocations[0].pool_id == "spec_shot"
    assert recipe.cap_breaker_allocations[0].rating_gain == 2


def test_unpermitted_specialization_is_unsupported() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = solve_locked_body(
        ruleset.bundle,
        _request(
            [_pair("toy_shot", 82), _pair("toy_finish", 40)],
            cap_breakers={
                "pools": [
                    {
                        "id": "spec_other",
                        "kind": "specialization",
                        "category": "toy_other",
                        "available": 1,
                    }
                ]
            },
        ),
    )
    assert outcome.status == "unsupported"
    assert outcome.recommendation is None
    assert "infeasible" not in _text(outcome)
    assert "illegal" in _text(outcome)


def test_target_below_minimum_is_proven_impossible() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = solve_locked_body(
        ruleset.bundle,
        _request([_pair("toy_shot", 5), _pair("toy_finish", 40)]),
    )
    assert outcome.status == "infeasible_proven"
    assert outcome.optimality_proven is True
    assert outcome.recommendation is None
    assert "minimum" in _text(outcome)
    assert "10" in _text(outcome)


def test_target_above_maximum_without_breakers_is_proven_impossible() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = solve_locked_body(
        ruleset.bundle,
        _request([_pair("toy_shot", 90), _pair("toy_finish", 40)]),
    )
    assert outcome.status == "infeasible_proven"
    assert "88" in _text(outcome)


def test_target_above_maximum_with_breakers_is_unsupported() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = solve_locked_body(
        ruleset.bundle,
        _request(
            [_pair("toy_shot", 90), _pair("toy_finish", 40)],
            cap_breakers={"pools": [{"id": "general", "kind": "unrestricted", "available": 1}]},
        ),
    )
    assert outcome.status == "unsupported"
    assert "infeasible" not in _text(outcome)
    assert "+1" in _text(outcome)


def test_link_conflict_without_breakers_is_proven() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = solve_locked_body(
        ruleset.bundle,
        _request([_pair("toy_shot", 80), _pair("toy_finish", 10)]),
    )
    assert outcome.status == "infeasible_proven"
    assert "forces 40" in _text(outcome)


def test_link_conflict_with_breakers_is_not_called_impossible() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = solve_locked_body(
        ruleset.bundle,
        _request(
            [_pair("toy_shot", 80), _pair("toy_finish", 10)],
            cap_breakers={"pools": [{"id": "general", "kind": "unrestricted", "available": 5}]},
        ),
    )
    assert outcome.status == "unsupported"
    assert outcome.recommendation is None
    assert "infeasible" not in _text(outcome)
    assert "impossible" not in _text(outcome)


def test_required_badge_that_contradicts_the_rating_is_proven() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = solve_locked_body(
        ruleset.bundle,
        _request(
            [_pair("toy_shot", 79), _pair("toy_finish", 40)],
            badges=[{"id": "toy_badge", "minimum_tier": "gold", "importance": "required"}],
        ),
    )
    assert outcome.status == "infeasible_proven"
    assert "79" in _text(outcome)
    assert "80" in _text(outcome)


def test_unobserved_final_is_unsupported() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = solve_locked_body(
        ruleset.bundle,
        _request(
            [_pair("toy_shot", 81), _pair("toy_finish", 40)],
            cap_breakers={"pools": [{"id": "general", "kind": "unrestricted", "available": 5}]},
        ),
    )
    assert outcome.status == "unsupported"
    assert "infeasible" not in _text(outcome)
    assert "+1" in _text(outcome)


def test_sg_without_bounds_is_unsupported() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = solve_locked_body(
        ruleset.bundle,
        _request(
            [_pair("toy_shot", 80), _pair("toy_finish", 40)],
            body=_locked_body(position="SG", height=71, weight=171, wingspan=71),
        ),
    )
    assert outcome.status == "unsupported"
    assert "not judged legal or illegal" in _text(outcome)
    assert "infeasible" not in _text(outcome)


def test_body_outside_a_complete_list_is_proven_illegal() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = solve_locked_body(
        ruleset.bundle,
        _request(
            [_pair("toy_shot", 80), _pair("toy_finish", 40)],
            body=_locked_body(height=71),
        ),
    )
    assert outcome.status == "infeasible_proven"
    assert "contradicts the verified body list" in _text(outcome)


def test_unlocked_body_is_not_searched() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    body = _locked_body()
    body["height_in"] = {"value": 70, "locked": False}
    outcome = solve_locked_body(
        ruleset.bundle,
        _request([_pair("toy_shot", 80)], body=body),
    )
    assert outcome.status == "unsupported"
    assert "not searched" in _text(outcome)


def test_expired_budget_is_inconclusive() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = solve_locked_body(
        ruleset.bundle,
        _request([_pair("toy_shot", 80), _pair("toy_finish", 40)]),
        SolveBudget(deadline=time.monotonic() - 1),
    )
    assert outcome.status == "no_feasible_found_in_budget"
    assert outcome.optimality_proven is False
    assert outcome.recommendation is None
    assert "infeasible" not in _text(outcome)
    assert "impossible" not in _text(outcome)
    assert "illegal" in _text(outcome)


def test_prioritized_miss_is_explained_and_still_legal() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = solve_locked_body(
        ruleset.bundle,
        _request(
            [_pair("toy_shot", 70, "prioritized"), _pair("toy_finish", 40)],
        ),
    )
    recipe = outcome.recommendation
    assert outcome.status == "complete_proven"
    assert recipe is not None
    assert recipe.score == 0
    assert recipe.final_attributes[0].rating == 80
    assert recipe.deviations[0].requested == 70
    assert recipe.deviations[0].achieved == 80


def test_forced_link_is_named_on_a_soft_target() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = solve_locked_body(
        ruleset.bundle,
        _request(
            [_pair("toy_shot", 80), _pair("toy_finish", 10, "prioritized")],
        ),
    )
    recipe = outcome.recommendation
    assert outcome.status == "complete_proven"
    assert recipe is not None
    assert "forces" in recipe.deviations[0].message
    assert recipe.deviations[0].achieved == 40


def test_unknown_badge_stays_unsupported() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = solve_locked_body(
        ruleset.bundle,
        _request(
            [_pair("toy_shot", 80), _pair("toy_finish", 40)],
            badges=[{"id": "missing_badge", "minimum_tier": "gold", "importance": "required"}],
        ),
    )
    assert outcome.status == "unsupported"
    assert "missing_badge" in _text(outcome)
    assert "ineligible" in _text(outcome)


def test_refine_rejects_a_different_body() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = solve_locked_body(
        ruleset.bundle,
        _request(
            [_pair("toy_shot", 80), _pair("toy_finish", 40)],
            mode="refine",
            reference={
                "body": {
                    "build_type": "male",
                    "position": "PG",
                    "height_in": 71,
                    "weight_lb": 170,
                    "wingspan_in": 70,
                },
                "base_attributes": [
                    {"id": "toy_shot", "rating": 80},
                    {"id": "toy_finish", "rating": 40},
                ],
            },
        ),
    )
    assert outcome.status == "unsupported"
    assert "reference body" in _text(outcome)


def test_refine_keeps_the_locked_reference() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = solve_locked_body(
        ruleset.bundle,
        _request(
            [_pair("toy_shot", 80), _pair("toy_finish", 40)],
            mode="refine",
            reference={
                "body": {
                    "build_type": "male",
                    "position": "PG",
                    "height_in": 70,
                    "weight_lb": 170,
                    "wingspan_in": 70,
                },
                "base_attributes": [
                    {"id": "toy_shot", "rating": 80},
                    {"id": "toy_finish", "rating": 40},
                ],
            },
        ),
    )
    assert outcome.status == "complete_proven"
    assert outcome.recommendation is not None
    assert "reference" in _text(outcome)


def test_validator_accepts_the_observed_recipe_and_rejects_tampering() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    request = _request(
        [_pair("toy_shot", 80), _pair("toy_finish", 40)],
        cap_breakers={"pools": [{"id": "general", "kind": "unrestricted", "available": 1}]},
    )
    query = query_from_body(request.body)
    observed = Candidate(
        base={"toy_shot": 80, "toy_finish": 40},
        final={"toy_shot": 80, "toy_finish": 40},
        allocations=(),
        name="TOY_ARCHETYPE",
        overall=70,
    )
    check = validate_recipe(ruleset.bundle, request, query, observed)
    assert check.problems == ()
    assert check.badges[0].highest_tier is BadgeTier.gold

    renamed = Candidate(
        base=observed.base,
        final=observed.final,
        allocations=(),
        name="NOT_THE_ARCHETYPE",
        overall=70,
    )
    renamed_check = validate_recipe(ruleset.bundle, request, query, renamed)
    assert any("NOT_THE_ARCHETYPE" in problem for problem in renamed_check.problems)

    assumed = Candidate(
        base={"toy_shot": 80, "toy_finish": 40},
        final={"toy_shot": 81, "toy_finish": 40},
        allocations=(Allocation("general", "toy_shot", 1, 1),),
        name="TOY_ARCHETYPE",
        overall=70,
    )
    assumed_check = validate_recipe(ruleset.bundle, request, query, assumed)
    assert assumed_check.problems
    assert any("+2" in problem for problem in assumed_check.problems)


def test_cp_status_mapping_keeps_timeout_distinct() -> None:
    assert classify_cp_status(cp_model.OPTIMAL, True) is SolveClassification.proven
    assert classify_cp_status(cp_model.FEASIBLE, True) is SolveClassification.feasible
    assert classify_cp_status(cp_model.INFEASIBLE, False) is SolveClassification.infeasible
    assert classify_cp_status(cp_model.UNKNOWN, False) is SolveClassification.inconclusive
    with pytest.raises(RuntimeError, match="invalid"):
        classify_cp_status(cp_model.MODEL_INVALID, False)


def test_synthetic_rules_are_not_served() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    response = plan_optimize(
        ruleset,
        _request([_pair("toy_shot", 80), _pair("toy_finish", 40)]),
        "req-synthetic",
        SolveBudget(),
    )
    assert response.status == "unsupported"
    assert response.recommendations.top == []
    assert "Search was not run" in response.warnings[0]


def test_non_synthetic_guard_copy_returns_the_toy_recipe(
    client: TestClient,
    tmp_path: Path,
) -> None:
    published = tmp_path / "published"
    published.mkdir()
    for path in _GUARD.iterdir():
        text = path.read_text(encoding="utf-8").replace("synthetic: true", "synthetic: false")
        (published / path.name).write_text(text, encoding="utf-8")
    client.app.state.ruleset = load_ruleset(published, allow_synthetic=False)
    response = client.post(
        "/api/v1/optimize",
        json={
            "body": _locked_body(),
            "attribute_targets": [
                {"id": "toy_shot", "target": 80, "importance": "required"},
                {"id": "toy_finish", "target": 40, "importance": "required"},
            ],
            "badges": [{"id": "toy_badge", "minimum_tier": "gold", "importance": "required"}],
            "animations": [{"id": "toy_anim", "importance": "required"}],
            "takeovers": [{"id": "toy_takeover", "importance": "required"}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete_proven"
    assert body["optimality_proven"] is True
    assert body["optimizer_version"] == "optimizer-m3-multi-body"
    recipe = body["recommendations"]["top"][0]
    assert recipe["name"] == "TOY_ARCHETYPE"
    assert recipe["verification"] == "verified"
    assert recipe["base_attributes"] == [
        {"id": "toy_shot", "rating": 80},
        {"id": "toy_finish", "rating": 40},
    ]
    assert recipe["eligible_badges"] == [{"id": "toy_badge", "highest_tier": "gold"}]
    assert body["recommendations"]["alternatives"] == []
    assert body["cache"]["hit"] is False
    assert "TOY_ARCHETYPE" in response.text
