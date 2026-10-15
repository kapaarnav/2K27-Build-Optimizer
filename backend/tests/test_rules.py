from pathlib import Path

import pytest
from pydantic import ValidationError

from app.rules.loader import digest_directory, load_active_ruleset, load_ruleset


def test_shipped_rules_do_not_enable_recommendations() -> None:
    ruleset = load_active_ruleset()
    assert ruleset.manifest.ruleset_id == "nba2k27-unverified"
    assert ruleset.manifest.coverage == []
    assert ruleset.manifest.synthetic is False
    assert ruleset.synthetic is False
    assert ruleset.recommendations_enabled is False
    assert ruleset.bundle.attributes.attributes == []
    assert ruleset.bundle.attributes.catalog_complete is False
    assert ruleset.bundle.bodies.bodies == []
    assert ruleset.files_sha256 == digest_directory(
        Path(__file__).parents[1] / "app" / "data" / "active"
    )


def test_digest_changes_when_rules_change(tmp_path: Path) -> None:
    rules = tmp_path / "manifest.yaml"
    rules.write_text("ruleset_id: one\ngame: nba2k27\ncoverage: []\n", encoding="utf-8")
    first = digest_directory(tmp_path)
    rules.write_text("ruleset_id: two\ngame: nba2k27\ncoverage: []\n", encoding="utf-8")
    assert digest_directory(tmp_path) != first


def test_loader_rejects_undeclared_game_numbers(tmp_path: Path) -> None:
    (tmp_path / "manifest.yaml").write_text(
        "ruleset_id: bad\ngame: nba2k27\ncoverage: []\nattribute_cost: 12\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_ruleset(tmp_path)


def test_loader_rejects_a_partial_rules_directory(tmp_path: Path) -> None:
    (tmp_path / "manifest.yaml").write_text(
        "ruleset_id: partial\ngame: nba2k27\ncoverage: []\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing"):
        load_ruleset(tmp_path)


def test_loader_rejects_verified_coverage_without_records(tmp_path: Path) -> None:
    destination = _copy_active(tmp_path / "claimed")
    manifest = destination / "manifest.yaml"
    manifest.write_text(
        "\n".join(
            [
                "ruleset_id: claimed",
                "game: nba2k27",
                "coverage:",
                "  - position: PG",
                "    body_profiles: verified",
                "    attribute_costs: unsupported",
                "    cap_breakers: unsupported",
                "    badge_eligibility: unsupported",
                "    animations: unsupported",
                "    takeovers: unsupported",
                "    archetype_names: unsupported",
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="body_profiles"):
        load_ruleset(destination)


def test_loader_rejects_extra_files_and_missing_evidence(tmp_path: Path) -> None:
    extra = _copy_active(tmp_path / "extra")
    (extra / "secret_costs.yaml").write_text("overall: 99\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unrecognized"):
        load_ruleset(extra)

    missing_evidence = _copy_active(tmp_path / "evidence")
    (missing_evidence / "attributes.yaml").write_text(
        "\n".join(
            [
                "catalog_complete: false",
                "attributes:",
                "  - id: toy_shot",
                "    label: Toy shot",
                "    category: toy",
                "    status: verified",
                "    synthetic: false",
                "    provenance:",
                "      source: missing evidence",
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="observed_at"):
        load_ruleset(missing_evidence)


def test_synthetic_guard_cannot_become_the_active_ruleset(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Synthetic"):
        load_ruleset(_GUARD, allow_synthetic=False)

    loaded = load_ruleset(_GUARD, allow_synthetic=True)
    assert loaded.synthetic is True
    assert loaded.recommendations_enabled is False
    assert loaded.manifest.fully_verified_positions()

    published = _copy_tree(_GUARD, tmp_path / "published")
    for path in published.glob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("synthetic: true", "synthetic: false"), encoding="utf-8")
    ruleset = load_ruleset(published, allow_synthetic=False)
    assert ruleset.synthetic is False
    assert ruleset.recommendations_enabled is True
    assert ruleset.manifest.ruleset_id == "synthetic-guard"


def test_active_files_do_not_embed_observation_numbers() -> None:
    active = Path(__file__).parents[1] / "app" / "data" / "active"
    text = "\n".join(path.read_text(encoding="utf-8") for path in active.glob("*.yaml"))
    assert "synthetic: true" not in text
    assert "overall:" not in text
    assert "rating_gain:" not in text
    assert "TOY_ARCHETYPE" not in text


def _copy_active(destination: Path) -> Path:
    return _copy_tree(Path(__file__).parents[1] / "app" / "data" / "active", destination)


def _copy_tree(source: Path, destination: Path) -> Path:
    destination.mkdir(parents=True)
    for path in source.iterdir():
        if path.is_file():
            (destination / path.name).write_bytes(path.read_bytes())
    return destination


_GUARD = Path(__file__).parents[1] / "tests" / "fixtures" / "synthetic" / "guard"
