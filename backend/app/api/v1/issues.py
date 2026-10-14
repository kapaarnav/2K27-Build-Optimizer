from fastapi import APIRouter

from app.api.errors import ApiError
from app.schemas.errors import ErrorResponse
from app.schemas.sharing import IssueReportRequest

router = APIRouter(tags=["issues"])


@router.post(
    "/issue-reports",
    status_code=501,
    responses={501: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def create_issue_report(_body: IssueReportRequest) -> None:
    raise ApiError(
        status_code=501,
        code="not_implemented",
        message="Issue reports are not available in this version.",
    )
