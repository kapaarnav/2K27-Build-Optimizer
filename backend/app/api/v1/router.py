from fastapi import APIRouter

from app.api.v1 import issues, metadata, optimize, shares, validate

router = APIRouter(prefix="/api/v1")
router.include_router(metadata.router)
router.include_router(validate.router)
router.include_router(optimize.router)
router.include_router(shares.router)
router.include_router(issues.router)
