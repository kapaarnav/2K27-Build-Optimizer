import pytest
from fastapi.testclient import TestClient

from app.domain import MECHANIC_FIELDS, Position, VerificationStatus
from app.rules.loader import ActiveRuleset
from app.rules.manifest import PositionCoverage, RulesManifest
from app.schemas.optimize import OptimizeRequest
from app.services.planning import assess_coverage


def _coverage(position: Position, status: VerificationStatus) -> PositionCoverage:
    values = {name: status for name in MECHANIC_FIELDS}
    return PositionCoverage(position=position, **values)


def _ruleset(entries: list[PositionCoverage], notes: list[str] | None = None) -> ActiveRuleset:
    return ActiveRuleset(
        manifest=RulesManifest(
            ruleset_id="test-rules",
            coverage=entries,
            notes=notes or ["No verified coverage."],
        ),
        files_sha256="ab" * 32,
    )


def _request(**overrides: object) -> OptimizeRequest:
    payload: dict[str, object] = {
        "attribute_targets": [
            {"id": "three_point", "target": 89, "importance": "required"},
        ]
    }
    payload.update(overrides)
    return OptimizeRequest.model_validate(payload)


def test_empty_rules_are_unsupported() -> None:
    decision = assess_coverage(_ruleset([]), _request())
    assert decision.supported is False
    assert decision.missing_mechanics == list(MECHANIC_FIELDS)


def test_locked_verified_position_is_supported() -> None:
    ruleset = _ruleset([_coverage(Position.pg, VerificationStatus.verified)])
    decision = assess_coverage(
        ruleset,
        _request(body={"position": {"value": "PG", "locked": True}}),
    )
    assert decision.supported is True
    assert decision.missing_mechanics == []


def test_locked_unverified_position_is_unsupported_not_infeasible() -> None:
    ruleset = _ruleset([_coverage(Position.center, VerificationStatus.verified)])
    decision = assess_coverage(
        ruleset,
        _request(body={"position": {"value": "PG", "locked": True}}),
    )
    assert decision.supported is False
    assert "PG" in decision.notes[0]
    assert "infeasible" not in decision.notes[0].lower()


def test_unlocked_preference_can_use_another_verified_position() -> None:
    ruleset = _ruleset([_coverage(Position.center, VerificationStatus.verified)])
    decision = assess_coverage(
        ruleset,
        _request(body={"position": {"value": "PG", "locked": False}}),
    )
    assert decision.supported is True


def test_partial_position_coverage_is_not_fully_verified() -> None:
    entry = _coverage(Position.pg, VerificationStatus.verified)
    entry = entry.model_copy(update={"archetype_names": VerificationStatus.unsupported})
    ruleset = _ruleset([entry])
    decision = assess_coverage(
        ruleset,
        _request(body={"position": {"value": "PG", "locked": True}}),
    )
    assert decision.supported is False
    assert decision.missing_mechanics == ["archetype_names"]


def test_illustrative_request_is_not_recommended(
    client: TestClient,
    illustrative_request: dict[str, object],
) -> None:
    response = client.post("/api/v1/optimize", json=illustrative_request)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unsupported"
    assert body["optimality_proven"] is False
    assert body["recommendations"] == {"top": [], "alternatives": []}
    assert body["coverage"]["supported"] is False
    assert "Search was not run" in body["warnings"][0]
    assert "traceback" not in response.text.lower()
    assert body["ruleset_id"] == "nba2k27-unverified"


def test_validate_does_not_judge_legality_without_rules(
    client: TestClient, illustrative_request: dict
) -> None:
    response = client.post("/api/v1/validate", json=illustrative_request)
    assert response.status_code == 200
    body = response.json()
    assert body["supported"] is False
    assert body["issues"][0]["code"] == "coverage_unsupported"
    codes = {issue["code"] for issue in body["issues"]}
    assert {
        "attribute_catalog_unverified",
        "body_profiles_unverified",
        "linked_attributes_unverified",
        "attribute_costs_unverified",
        "archetype_names_unverified",
        "cap_breakers_unverified",
        "badge_unverified",
    } <= codes
    badge = next(issue for issue in body["issues"] if issue["code"] == "badge_unverified")
    assert "set_and_fire" in badge["message"]
    assert "unsupported" in badge["message"].lower()
    assert "infeasible" not in response.text.lower()


def test_locked_female_body_is_not_called_illegal(client: TestClient) -> None:
    response = client.post(
        "/api/v1/validate",
        json={
            "attribute_targets": [
                {"id": "three_point", "target": 89, "importance": "required"},
            ],
            "body": {"build_type": {"value": "female", "locked": True}},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["supported"] is False
    messages = " ".join(issue["message"] for issue in body["issues"])
    assert "not judged legal or illegal" in messages
    assert "infeasible" not in response.text.lower()


def test_locked_build_type_needs_a_value(client: TestClient) -> None:
    response = client.post(
        "/api/v1/optimize",
        json={
            "attribute_targets": [
                {"id": "three_point", "target": 89, "importance": "required"},
            ],
            "body": {"build_type": {"value": None, "locked": True}},
        },
    )
    assert response.status_code == 422
    assert "locked field" in response.text.lower()


def test_metadata_has_no_attribute_dictionary(client: TestClient) -> None:
    response = client.get("/api/v1/metadata")
    assert response.status_code == 200
    body = response.json()
    assert body["recommendations_enabled"] is False
    assert body["attributes"] == []
    assert body["badges"] == []
    assert body["animations"] == []
    assert body["takeovers"] == []
    assert body["badge_tiers"] == ["bronze", "silver", "gold", "hall_of_fame"]
    assert body["coverage"] == []
    assert body["positions"] == ["PG", "SG", "SF", "PF", "C"]
    assert body["build_types"] == ["male", "female"]
    assert "Unofficial" in body["disclaimer"]
    assert len(body["files_sha256"]) == 64


@pytest.mark.parametrize(
    ("payload", "fragment"),
    [
        ({"attribute_targets": []}, "at least 1"),
        (
            {
                "attribute_targets": [
                    {"id": "three_point", "target": 89, "importance": "required"},
                    {"id": "three_point", "target": 90, "importance": "normal"},
                ]
            },
            "unique",
        ),
        (
            {
                "attribute_targets": [
                    {"id": "three_point", "target": 89, "importance": "required"}
                ],
                "body": {"position": {"value": None, "locked": True}},
            },
            "locked field",
        ),
        (
            {
                "attribute_targets": [
                    {"id": "three_point", "target": 89, "importance": "required"}
                ],
                "cap_breakers": {"pools": [], "reserved_total": 2},
            },
            "Reserved",
        ),
        (
            {
                "attribute_targets": [
                    {"id": "three_point", "target": 89, "importance": "required"}
                ],
                "playstyle": "meta",
            },
            "playstyle",
        ),
        (
            {
                "attribute_targets": [
                    {"id": "three_point", "target": 89, "importance": "required"}
                ],
                "mode": "refine",
            },
            "reference build",
        ),
        (
            {
                "attribute_targets": [
                    {"id": "three_point", "target": 89, "importance": "required"}
                ],
                "not_a_field": True,
            },
            "Extra inputs",
        ),
    ],
)
def test_invalid_requests_are_422(client: TestClient, payload: dict, fragment: str) -> None:
    response = client.post("/api/v1/optimize", json=payload)
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "invalid_request"
    assert body["request_id"]
    assert "traceback" not in response.text.lower()
    assert fragment.lower() in response.text.lower()


def test_specialization_pool_requires_a_category(client: TestClient) -> None:
    response = client.post(
        "/api/v1/optimize",
        json={
            "attribute_targets": [{"id": "three_point", "target": 89, "importance": "required"}],
            "cap_breakers": {
                "pools": [{"id": "spec_shooting", "kind": "specialization", "available": 1}]
            },
        },
    )
    assert response.status_code == 422
    assert "category" in response.text.lower()


def test_share_and_reports_are_not_implemented(client: TestClient) -> None:
    candidate = {
        "build_id": "synthetic-1",
        "name": "SYNTHETIC_NOT_A_RECOMMENDATION",
        "rank": 1,
        "score": 1,
        "body": {
            "build_type": "male",
            "position": "PG",
            "height_in": 76,
            "weight_lb": 180,
            "wingspan_in": 78,
        },
        "base_attributes": [{"id": "three_point", "rating": 80}],
        "final_attributes": [{"id": "three_point", "rating": 80}],
        "cap_breaker_allocations": [],
        "eligible_badges": [],
        "eligible_animations": [],
        "eligible_takeovers": [],
        "score_breakdown": {"scoring_version": "score-unconfigured", "components": []},
        "deviations": [],
        "verification": "verified",
    }
    share = client.post("/api/v1/shared-builds", json={"candidate": candidate})
    assert share.status_code == 501
    assert share.json()["code"] == "not_implemented"
    assert "SYNTHETIC_NOT_A_RECOMMENDATION" not in share.text

    loaded = client.get("/api/v1/shared-builds/share_123")
    assert loaded.status_code == 501
    assert loaded.json()["code"] == "not_implemented"

    report = client.post(
        "/api/v1/issue-reports",
        json={"category": "other", "description": "Checking the contract."},
    )
    assert report.status_code == 501
    assert report.json()["code"] == "not_implemented"


def test_openapi_lists_contract_paths(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = set(schema["paths"])
    assert paths >= {
        "/health/live",
        "/health/ready",
        "/api/v1/metadata",
        "/api/v1/validate",
        "/api/v1/optimize",
        "/api/v1/shared-builds",
        "/api/v1/shared-builds/{share_id}",
        "/api/v1/issue-reports",
    }
