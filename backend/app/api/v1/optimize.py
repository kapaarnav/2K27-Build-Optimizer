import time

from fastapi import APIRouter, Request

from app.request_context import current_request_id
from app.rules.loader import ActiveRuleset
from app.schemas.optimize import OptimizeRequest, OptimizeResponse, UnsupportedOptimizeResponse
from app.services.planning import assess_coverage, unsupported_optimize

router = APIRouter(tags=["optimize"])


@router.post("/optimize", response_model=OptimizeResponse)
def optimize_build(body: OptimizeRequest, request: Request) -> UnsupportedOptimizeResponse:
    started = time.perf_counter()
    ruleset: ActiveRuleset = request.app.state.ruleset
    decision = assess_coverage(ruleset, body)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if decision.supported:
        raise RuntimeError("A supported ruleset has no optimizer in this version.")
    return unsupported_optimize(ruleset, decision, current_request_id(), elapsed_ms)
