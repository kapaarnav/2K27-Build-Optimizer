import time
from pathlib import Path

from app.optimizer.cpsat import solve_exact
from app.optimizer.portfolio import search_bodies
from app.optimizer.solve import SolveBudget
from app.rules.loader import load_ruleset
from app.schemas.optimize import OptimizeRequest

_GUARD = Path(__file__).parent / "fixtures" / "synthetic" / "guard"


def _open_pg(height: int | None) -> dict[str, object]:
    return {
        "build_type": {"value": "male", "locked": True},
        "position": {"value": "PG", "locked": True},
        "height_in": {"value": height, "locked": False},
        "weight_lb": {"value": None, "locked": False},
        "wingspan_in": {"value": None, "locked": False},
    }


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
    parts.extend(item.message for item in outcome.unmet)
    return " ".join(parts).lower()


def _names(outcome) -> list[str]:
    return [item.name for item in outcome.recommendations]


def test_preference_breaks_ties_after_target_misses() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = search_bodies(
        ruleset.bundle,
        _request(
            [_pair("toy_shot", 80, "prioritized"), _pair("toy_finish", 40)],
            body=_open_pg(74),
        ),
    )
    assert outcome.status == "complete_proven"
    assert outcome.optimality_proven is True
    assert _names(outcome)[:3] == ["TOY_TALL", "TOY_ARCHETYPE", "TOY_LOW"]
    assert outcome.recommendations[0].body.height_in == 74
    assert outcome.recommendations[1].body.height_in == 70
    low = next(item for item in outcome.recommendations if item.name == "TOY_LOW")
    exact = next(item for item in outcome.recommendations if item.name == "TOY_ARCHETYPE")
    assert low.rank > exact.rank


def test_playstyle_is_recorded_and_does_not_reorder() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    shooting = search_bodies(
        ruleset.bundle,
        _request(
            [_pair("toy_shot", 80, "prioritized"), _pair("toy_finish", 40)],
            body=_open_pg(74),
            playstyle="shooting",
        ),
    )
    defense = search_bodies(
        ruleset.bundle,
        _request(
            [_pair("toy_shot", 80, "prioritized"), _pair("toy_finish", 40)],
            body=_open_pg(74),
            playstyle="defense",
        ),
    )
    assert _names(shooting) == _names(defense)
    note = next(
        item
        for item in shooting.recommendations[0].score_breakdown.components
        if item.id == "playstyle"
    )
    assert note.weight == 0
    assert "shooting" in note.note
    assert "does not change rank" in note.note


def test_upgrade_is_an_annotated_alternative() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = search_bodies(
        ruleset.bundle,
        _request(
            [_pair("toy_shot", 80), _pair("toy_finish", 40, "normal")],
        ),
    )
    assert outcome.status == "complete_proven"
    assert [item.name for item in outcome.recommendations] == ["TOY_ARCHETYPE", "TOY_PLUS"]
    assert outcome.recommendations[1].score == 80
    alternative = outcome.alternatives[0]
    assert alternative.name == "TOY_PLUS"
    assert alternative.build_id == outcome.recommendations[1].build_id
    overlap = next(
        item for item in alternative.score_breakdown.components if item.id == "alternative_overlap"
    )
    assert overlap.value == 2
    assert "top rank 2" in overlap.note


def test_required_miss_returns_a_labeled_closest_build() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = search_bodies(
        ruleset.bundle,
        _request([_pair("toy_shot", 5), _pair("toy_finish", 40)]),
    )
    assert outcome.status == "infeasible_proven"
    assert outcome.optimality_proven is True
    recipe = outcome.recommendations[0]
    assert recipe.name == "TOY_ARCHETYPE"
    assert recipe.final_attributes[0].rating == 80
    assert recipe.score < 100
    unmet = outcome.unmet[0]
    assert unmet.requested == "5"
    assert unmet.achieved == "80"
    assert "minimum" in _text(outcome)
    assert "game rules were not relaxed" in _text(outcome)


def test_locked_illegal_body_relaxes_only_the_lock() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = search_bodies(
        ruleset.bundle,
        _request(
            [_pair("toy_shot", 80), _pair("toy_finish", 40)],
            body=_locked_body(height=71),
        ),
    )
    assert outcome.status == "infeasible_proven"
    recipe = outcome.recommendations[0]
    assert recipe.body.height_in == 70
    assert recipe.name == "TOY_ARCHETYPE"
    height = next(item for item in outcome.unmet if item.field == "body.height_in")
    assert height.requested == "71"
    assert height.achieved == "70"
    assert "contradicts the verified body list" in _text(outcome)


def test_incomplete_position_range_is_not_called_optimal() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    body = _open_pg(None)
    body["position"] = {"value": None, "locked": False}
    body["build_type"] = {"value": "male", "locked": True}
    outcome = search_bodies(
        ruleset.bundle,
        _request([_pair("toy_shot", 80), _pair("toy_finish", 40)], body=body),
    )
    assert outcome.status == "partial_feasible"
    assert outcome.optimality_proven is False
    assert "toy_sg" in _text(outcome)
    assert "not a proven top 5" in _text(outcome)
    assert "impossible" not in _text(outcome)


def test_expired_portfolio_budget_does_not_invent_a_closest_build() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = search_bodies(
        ruleset.bundle,
        _request([_pair("toy_shot", 5), _pair("toy_finish", 40)]),
        SolveBudget(deadline=time.monotonic() - 1),
    )
    assert outcome.status == "no_feasible_found_in_budget"
    assert outcome.recommendations == ()
    assert outcome.unmet == ()
    assert "illegal" in _text(outcome)


def test_stopping_early_does_not_claim_a_proven_top_five(monkeypatch) -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    budget = SolveBudget(deadline=time.monotonic() + 30)
    real = solve_exact

    def expire_after_first(*args, **kwargs):
        found = real(*args, **kwargs)
        object.__setattr__(budget, "deadline", time.monotonic() - 1)
        return found

    monkeypatch.setattr("app.optimizer.portfolio.solve_exact", expire_after_first)
    outcome = search_bodies(
        ruleset.bundle,
        _request(
            [_pair("toy_shot", 80, "prioritized"), _pair("toy_finish", 40)],
            body=_open_pg(74),
        ),
        budget,
    )
    assert outcome.status == "partial_feasible"
    assert outcome.optimality_proven is False
    assert outcome.recommendations
    assert len(outcome.recommendations) < 5
    assert "not a proven top 5" in _text(outcome)


def test_refine_relaxes_a_required_target_without_leaving_the_reference_body() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    outcome = search_bodies(
        ruleset.bundle,
        _request(
            [_pair("toy_shot", 5), _pair("toy_finish", 40)],
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
    assert outcome.status == "infeasible_proven"
    recipe = outcome.recommendations[0]
    assert recipe.body.height_in == 70
    assert recipe.name == "TOY_ARCHETYPE"
    assert outcome.unmet[0].requested == "5"
    assert recipe.body.height_in == 70
