from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_exception_handlers
from app.api.health import router as health_router
from app.api.middleware import RequestIdMiddleware
from app.api.v1.router import router as v1_router
from app.config import get_settings
from app.db.session import create_db_engine
from app.domain import DISCLAIMER
from app.rules.loader import load_active_ruleset


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.settings = settings
    app.state.ruleset = load_active_ruleset()
    app.state.engine = create_db_engine(settings.database_url)
    try:
        yield
    finally:
        app.state.engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Unofficial NBA 2K27 Build Optimizer API",
        version="0.1.0",
        description=DISCLAIMER,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)
    install_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(v1_router)
    return app


app = create_app()
