from fastapi import APIRouter, Request

from app.request_context import current_request_id
from app.rules.loader import ActiveRuleset
from app.schemas.optimize import OptimizeRequest, ValidateResponse
from app.services.planning import validation_result

router = APIRouter(tags=["validate"])


@router.post("/validate", response_model=ValidateResponse)
def validate_build(body: OptimizeRequest, request: Request) -> ValidateResponse:
    ruleset: ActiveRuleset = request.app.state.ruleset
    return validation_result(ruleset, body, current_request_id())
