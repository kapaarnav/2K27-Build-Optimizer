from datetime import date
from pathlib import Path

import yaml

from app.domain import BuildType, Position, VerificationStatus
from app.rules.engine import (
    BodyQuery,
    application_limit,
    archetype_name,
    assess_body,
    audit_request,
    badge_eligibility,
    cap_breaker_gain,
    exact_overall,
    propagate_links,
)
from app.rules.fixtures import FixtureFile, evaluate_case
from app.rules.loader import load_active_ruleset, load_ruleset
from app.rules.models import (
    AttributeDefinition,
    AttributesFile,
    LinkRule,
    LinkTable,
    RuleBundle,
)
from app.rules.provenance import Provenance
from app.schemas.optimize import OptimizeRequest

_GUARD = Path(__file__).parent / "fixtures" / "synthetic" / "guard"
_CASES = Path(__file__).parent / "fixtures" / "synthetic" / "cases.yaml"


def test_fixture_cases_match_the_synthetic_ruleset() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    assert ruleset.recommendations_enabled is False
    fixtures = FixtureFile.model_validate(yaml.safe_load(_CASES.read_text(encoding="utf-8")))
    for case in fixtures.cases:
        finding = evaluate_case(ruleset.bundle, case)
        expect = case.expect
        assert finding.status == expect.status, case.id
        assert finding.code == expect.code, case.id
        assert finding.legal == expect.legal, case.id
        assert finding.overall == expect.overall, case.id
        assert finding.name == expect.name, case.id
        assert finding.eligible == expect.eligible, case.id
        assert finding.highest_tier == expect.highest_tier, case.id
        assert finding.rating_gain == expect.rating_gain, case.id
        assert finding.limit == expect.limit, case.id
        assert finding.allowed == expect.allowed, case.id
        forced = {item.attribute_id: item.minimum for item in finding.forced_minima}
        assert forced == expect.forced, case.id
        for word in expect.absent_words:
            assert word not in finding.message.lower(), case.id


def test_active_rules_reject_configurations_without_guessing() -> None:
    bundle = load_active_ruleset().bundle
    query = BodyQuery(
        build_type=BuildType.female,
        position=Position.pg,
        height_in=76,
        weight_lb=180,
        wingspan_in=80,
        build_type_locked=True,
        position_locked=True,
        height_locked=True,
        weight_locked=True,
        wingspan_locked=True,
    )
    body = assess_body(bundle, query)
    assert body.status == "unsupported"
    assert body.code == "body_profiles_unverified"
    assert "not judged legal or illegal" in body.message
    assert exact_overall(bundle, query, {}).code == "attribute_costs_unverified"
    assert archetype_name(bundle, query, {}).code == "archetype_names_unverified"
    badge = badge_eligibility(bundle, "set_and_fire", {}, "final", query)
    assert badge.status == "unsupported"
    assert badge.code == "badge_unverified"
    assert cap_breaker_gain(bundle, "toy_shot", 80, 1).code == "cap_breakers_unverified"
    assert propagate_links(bundle, {}).code == "linked_attributes_unverified"
    assert application_limit(bundle).code == "cap_breaker_limit_unverified"


def test_complete_catalog_names_unknown_attributes() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    request = OptimizeRequest.model_validate(
        {
            "attribute_targets": [
                {"id": "three_point", "target": 89, "importance": "required"},
            ]
        }
    )
    findings = audit_request(ruleset.bundle, request)
    unknown = next(finding for finding in findings if finding.code == "unknown_attribute")
    assert unknown.status == "unsupported"
    assert "three_point" in unknown.message
    assert all(finding.code != "body_not_fully_specified" for finding in findings)


def test_link_closure_is_transitive() -> None:
    provenance = Provenance(
        source="Synthetic fixture. Not an NBA 2K27 observation.",
        observed_at=date(2026, 1, 1),
        source_app_version="synthetic",
        evidence_ref="tests/unit",
    )
    attribute = {
        "status": VerificationStatus.verified,
        "synthetic": True,
        "provenance": provenance,
        "category": "toy",
    }
    bundle = RuleBundle(
        attributes=AttributesFile(
            catalog_complete=True,
            attributes=[
                AttributeDefinition(id="toy_shot", label="Toy shot", **attribute),
                AttributeDefinition(id="toy_finish", label="Toy finish", **attribute),
            ],
        ),
        links=LinkTable(
            complete=True,
            status=VerificationStatus.verified,
            synthetic=True,
            provenance=provenance,
            links=[
                LinkRule(
                    id="shot_raises_finish",
                    source_attribute_id="toy_shot",
                    target_attribute_id="toy_finish",
                    when_source_at_least=80,
                    target_minimum=40,
                    status=VerificationStatus.verified,
                    synthetic=True,
                    provenance=provenance,
                ),
                LinkRule(
                    id="finish_raises_shot",
                    source_attribute_id="toy_finish",
                    target_attribute_id="toy_shot",
                    when_source_at_least=40,
                    target_minimum=85,
                    status=VerificationStatus.verified,
                    synthetic=True,
                    provenance=provenance,
                ),
            ],
        ),
    )
    finding = propagate_links(bundle, {"toy_shot": 80, "toy_finish": 10})
    assert finding.status == "verified"
    assert {item.attribute_id: item.rating for item in finding.ratings} == {
        "toy_finish": 40,
        "toy_shot": 85,
    }


def test_partial_link_table_is_not_applied() -> None:
    provenance = Provenance(
        source="Synthetic fixture. Not an NBA 2K27 observation.",
        observed_at=date(2026, 1, 1),
        source_app_version="synthetic",
        evidence_ref="tests/unit",
    )
    bundle = RuleBundle(
        attributes=AttributesFile(
            catalog_complete=True,
            attributes=[
                AttributeDefinition(
                    id="toy_shot",
                    label="Toy shot",
                    category="toy",
                    status=VerificationStatus.verified,
                    synthetic=True,
                    provenance=provenance,
                ),
                AttributeDefinition(
                    id="toy_finish",
                    label="Toy finish",
                    category="toy",
                    status=VerificationStatus.verified,
                    synthetic=True,
                    provenance=provenance,
                ),
            ],
        ),
        links=LinkTable(
            complete=False,
            status=VerificationStatus.unsupported,
            synthetic=True,
            links=[
                LinkRule(
                    id="shot_raises_finish",
                    source_attribute_id="toy_shot",
                    target_attribute_id="toy_finish",
                    when_source_at_least=80,
                    target_minimum=40,
                    status=VerificationStatus.verified,
                    synthetic=True,
                    provenance=provenance,
                )
            ],
        ),
    )
    finding = propagate_links(bundle, {"toy_shot": 80, "toy_finish": 10})
    assert finding.code == "linked_attributes_unverified"
    assert finding.ratings == []
    assert finding.forced_minima == []
