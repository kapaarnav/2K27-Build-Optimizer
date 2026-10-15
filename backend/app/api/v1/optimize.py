from fastapi import APIRouter, Request

from app.config import Settings
from app.optimizer.solve import SolveBudget
from app.request_context import current_request_id
from app.rules.loader import ActiveRuleset
from app.schemas.optimize import OptimizeRequest, OptimizeResponse
from app.services.planning import plan_optimize

router = APIRouter(tags=["optimize"])


@router.post("/optimize", response_model=OptimizeResponse)
def optimize_build(body: OptimizeRequest, request: Request) -> OptimizeResponse:
    """Search verified bodies outside the event loop.

    FastAPI runs this synchronous handler on a threadpool. One request shares
    one deadline across bodies. The shipped ruleset has no verified coverage,
    so the response stays unsupported.
    """

    ruleset: ActiveRuleset = request.app.state.ruleset
    settings: Settings = request.app.state.settings
    return plan_optimize(
        ruleset,
        body,
        current_request_id(),
        SolveBudget(max_time_seconds=settings.solver_max_seconds),
    )
