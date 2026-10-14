from fastapi import APIRouter

from app.api.errors import ApiError
from app.schemas.errors import ErrorResponse
from app.schemas.sharing import ShareCreateRequest

router = APIRouter(tags=["shares"])


@router.post(
    "/shared-builds",
    status_code=501,
    responses={501: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def create_share(_body: ShareCreateRequest) -> None:
    raise ApiError(
        status_code=501,
        code="not_implemented",
        message=("Sharing is not available until a verified ruleset can revalidate the build."),
    )


@router.get(
    "/shared-builds/{share_id}",
    responses={501: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def read_share(share_id: str) -> None:
    if not share_id or len(share_id) > 80:
        raise ApiError(
            status_code=422,
            code="invalid_request",
            message="The share id is not valid.",
        )
    raise ApiError(
        status_code=501,
        code="not_implemented",
        message="Shared builds are not available in this version.",
    )
