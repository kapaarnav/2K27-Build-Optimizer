from fastapi import APIRouter, Request

from app.domain import (
    DISCLAIMER,
    OPTIMIZER_VERSION,
    PLAYSTYLES,
    SCORING_VERSION,
    Importance,
    Position,
)
from app.rules.loader import ActiveRuleset
from app.schemas.metadata import MetadataResponse, PlaystyleOption

router = APIRouter(tags=["metadata"])


@router.get("/metadata", response_model=MetadataResponse)
def metadata(request: Request) -> MetadataResponse:
    ruleset: ActiveRuleset = request.app.state.ruleset
    return MetadataResponse(
        ruleset_id=ruleset.manifest.ruleset_id,
        game=ruleset.manifest.game,
        scoring_version=SCORING_VERSION,
        optimizer_version=OPTIMIZER_VERSION,
        files_sha256=ruleset.files_sha256,
        disclaimer=DISCLAIMER,
        recommendations_enabled=ruleset.recommendations_enabled,
        positions=list(Position),
        importance_levels=list(Importance),
        playstyles=[PlaystyleOption(id=item_id, label=label) for item_id, label in PLAYSTYLES],
        attributes=[],
        coverage=list(ruleset.manifest.coverage),
        notes=list(ruleset.manifest.notes),
    )
