from collections.abc import Sequence

from fastapi import APIRouter, Request

from app.domain import (
    DISCLAIMER,
    OPTIMIZER_VERSION,
    PLAYSTYLES,
    SCORING_VERSION,
    BadgeTier,
    BuildType,
    Importance,
    Position,
    VerificationStatus,
)
from app.rules.loader import ActiveRuleset
from app.rules.models import EligibilityRule
from app.schemas.metadata import (
    AttributeDescriptor,
    MetadataResponse,
    PlaystyleOption,
    UnlockDescriptor,
)

router = APIRouter(tags=["metadata"])


def verified_unlocks(rules: Sequence[EligibilityRule]) -> list[UnlockDescriptor]:
    """One entry per verified id. Tiers stay on the request, not as separate catalog rows."""

    ids: list[str] = []
    for rule in rules:
        if rule.synthetic or rule.status is not VerificationStatus.verified:
            continue
        if rule.id not in ids:
            ids.append(rule.id)
    return [UnlockDescriptor(id=item, label=item) for item in ids]


@router.get("/metadata", response_model=MetadataResponse)
def metadata(request: Request) -> MetadataResponse:
    ruleset: ActiveRuleset = request.app.state.ruleset
    eligibility = ruleset.bundle.eligibility
    return MetadataResponse(
        ruleset_id=ruleset.manifest.ruleset_id,
        game=ruleset.manifest.game,
        scoring_version=SCORING_VERSION,
        optimizer_version=OPTIMIZER_VERSION,
        files_sha256=ruleset.files_sha256,
        disclaimer=DISCLAIMER,
        recommendations_enabled=ruleset.recommendations_enabled,
        positions=list(Position),
        build_types=list(BuildType),
        importance_levels=list(Importance),
        playstyles=[PlaystyleOption(id=item_id, label=label) for item_id, label in PLAYSTYLES],
        attributes=[
            AttributeDescriptor(id=item.id, label=item.label, category=item.category)
            for item in ruleset.bundle.attributes.attributes
            if item.status is VerificationStatus.verified and not item.synthetic
        ],
        badges=verified_unlocks(eligibility.badges),
        animations=verified_unlocks(eligibility.animations),
        takeovers=verified_unlocks(eligibility.takeovers),
        badge_tiers=list(BadgeTier),
        coverage=list(ruleset.manifest.coverage),
        notes=list(ruleset.manifest.notes),
    )
