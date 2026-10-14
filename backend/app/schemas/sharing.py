from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain import IssueCategory
from app.schemas.optimize import Recommendation


class ShareCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate: Recommendation


class ShareCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    share_id: str
    url: str
    validation_status: Literal["valid", "needs_verification", "outdated_confirmed"]


class SharedBuildResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    share_id: str
    snapshot: Recommendation
    ruleset_id: str
    scoring_version: str
    validation_status: Literal["valid", "needs_verification", "outdated_confirmed"]
    invalid_reasons: list[str] = Field(default_factory=list)


class IssueReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category: IssueCategory
    description: str = Field(default="", max_length=4000)
    share_id: str | None = Field(default=None, max_length=80)


class IssueReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str
    status: Literal["pending"]
