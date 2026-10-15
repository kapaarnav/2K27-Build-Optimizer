import hashlib
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.domain import MECHANIC_FIELDS
from app.rules.manifest import RulesManifest
from app.rules.models import (
    AttributesFile,
    BodiesFile,
    CapBreakerFile,
    CostsFile,
    EligibilityFile,
    LinkTable,
    NamesFile,
    RuleBundle,
    ensure_consistent,
)

ACTIVE_RULES_DIR = Path(__file__).resolve().parents[1] / "data" / "active"

KNOWN_FILES = frozenset(
    {
        "manifest.yaml",
        "attributes.yaml",
        "bodies.yaml",
        "links.yaml",
        "costs.yaml",
        "names.yaml",
        "eligibility.yaml",
        "cap_breakers.yaml",
    }
)


class ActiveRuleset(BaseModel):
    model_config = ConfigDict(frozen=True)

    manifest: RulesManifest
    bundle: RuleBundle = Field(default_factory=RuleBundle)
    files_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    synthetic: bool = False

    @property
    def recommendations_enabled(self) -> bool:
        if self.synthetic or self.manifest.synthetic or self.bundle.any_synthetic():
            return False
        positions = self.manifest.fully_verified_positions()
        if not positions:
            return False
        if not self.bundle.attributes.catalog_complete or not self.bundle.links_evaluable():
            return False
        return all(
            self.bundle.mechanic_is_backed(position, mechanic)
            for position in positions
            for mechanic in MECHANIC_FIELDS
        )


def digest_directory(directory: Path) -> str:
    hasher = hashlib.sha256()
    files = sorted(path for path in directory.rglob("*") if path.is_file())
    for path in files:
        hasher.update(path.relative_to(directory).as_posix().encode())
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def load_ruleset(directory: Path, *, allow_synthetic: bool = False) -> ActiveRuleset:
    manifest = _read_model(directory / "manifest.yaml", RulesManifest)
    _require_known_files(directory)
    bundle = RuleBundle(
        attributes=_read_model(directory / "attributes.yaml", AttributesFile),
        bodies=_read_model(directory / "bodies.yaml", BodiesFile),
        links=_read_model(directory / "links.yaml", LinkTable),
        costs=_read_model(directory / "costs.yaml", CostsFile),
        names=_read_model(directory / "names.yaml", NamesFile),
        eligibility=_read_model(directory / "eligibility.yaml", EligibilityFile),
        cap_breakers=_read_model(directory / "cap_breakers.yaml", CapBreakerFile),
    )
    ensure_consistent(bundle, manifest)
    synthetic = manifest.synthetic or bundle.any_synthetic()
    if synthetic and not allow_synthetic:
        raise ValueError("Synthetic rules cannot be loaded as the active ruleset.")
    return ActiveRuleset(
        manifest=manifest,
        bundle=bundle,
        files_sha256=digest_directory(directory),
        synthetic=synthetic,
    )


def load_active_ruleset() -> ActiveRuleset:
    return load_ruleset(ACTIVE_RULES_DIR, allow_synthetic=False)


def _require_known_files(directory: Path) -> None:
    names = {path.name for path in directory.iterdir() if path.is_file()}
    unknown = sorted(names - KNOWN_FILES)
    missing = sorted(KNOWN_FILES - names)
    if unknown:
        raise ValueError(f"Unrecognized rules files: {unknown}.")
    if missing:
        raise ValueError(f"Rules directory is missing {missing}.")


def _read_model[T: BaseModel](path: Path, model: type[T]) -> T:
    if not path.is_file():
        raise ValueError(f"Rules directory needs {path.name}.")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return model.model_validate(raw or {})
