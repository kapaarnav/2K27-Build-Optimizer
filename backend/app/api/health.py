from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.db.session import probe_database
from app.rules.loader import ActiveRuleset
from app.schemas.health import HealthLive, HealthReady

router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=HealthLive)
def live() -> HealthLive:
    return HealthLive(status="ok")


@router.get(
    "/health/ready",
    response_model=HealthReady,
    responses={503: {"model": HealthReady}},
)
def ready(request: Request) -> HealthReady | JSONResponse:
    ruleset: ActiveRuleset = request.app.state.ruleset
    connected = probe_database(request.app.state.engine)
    body = HealthReady(
        status="ok" if connected else "unavailable",
        database="connected" if connected else "unavailable",
        rules_loaded=True,
        recommendations_enabled=ruleset.recommendations_enabled,
    )
    if not connected:
        return JSONResponse(status_code=503, content=body.model_dump())
    return body
