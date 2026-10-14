import hashlib
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.rules.manifest import RulesManifest

ACTIVE_RULES_DIR = Path(__file__).resolve().parents[1] / "data" / "active"


class ActiveRuleset(BaseModel):
    model_config = ConfigDict(frozen=True)

    manifest: RulesManifest
    files_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @property
    def recommendations_enabled(self) -> bool:
        return bool(self.manifest.fully_verified_positions())


def digest_directory(directory: Path) -> str:
    hasher = hashlib.sha256()
    files = sorted(path for path in directory.rglob("*") if path.is_file())
    for path in files:
        hasher.update(path.relative_to(directory).as_posix().encode())
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def load_ruleset(directory: Path) -> ActiveRuleset:
    raw = (directory / "manifest.yaml").read_text(encoding="utf-8")
    manifest = RulesManifest.model_validate(yaml.safe_load(raw))
    return ActiveRuleset(manifest=manifest, files_sha256=digest_directory(directory))


def load_active_ruleset() -> ActiveRuleset:
    return load_ruleset(ACTIVE_RULES_DIR)
