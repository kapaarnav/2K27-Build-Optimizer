import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.request_context import current_request_id
from app.schemas.errors import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[ErrorDetail] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []
        super().__init__(message)


def _error_body(
    code: str,
    message: str,
    details: list[ErrorDetail] | None = None,
) -> dict[str, object]:
    return ErrorResponse(
        code=code,
        message=message,
        request_id=current_request_id(),
        details=details or [],
    ).model_dump()


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        details: list[ErrorDetail] = []
        for error in exc.errors():
            location = [str(part) for part in error.get("loc", []) if part != "body"]
            message = str(error.get("msg", "Invalid value."))
            prefix = "Value error, "
            if message.startswith(prefix):
                message = message.removeprefix(prefix)
            details.append(
                ErrorDetail(
                    field=".".join(location),
                    code=str(error.get("type", "invalid")),
                    message=message,
                )
            )
        return JSONResponse(
            status_code=422,
            content=_error_body(
                "invalid_request",
                "The request is not a valid build query.",
                details,
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error %s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content=_error_body(
                "internal_error",
                "The planning service hit an unexpected error. "
                "Retry once, then report the request id.",
            ),
        )
