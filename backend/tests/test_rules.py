from pathlib import Path

import pytest
from pydantic import ValidationError

from app.rules.loader import digest_directory, load_active_ruleset, load_ruleset


def test_shipped_rules_do_not_enable_recommendations() -> None:
    ruleset = load_active_ruleset()
    assert ruleset.manifest.ruleset_id == "nba2k27-unverified"
    assert ruleset.manifest.coverage == []
    assert ruleset.recommendations_enabled is False
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
