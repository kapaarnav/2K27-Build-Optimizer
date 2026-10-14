from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthLive(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]


class HealthReady(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "unavailable"]
    database: Literal["connected", "unavailable"]
    rules_loaded: bool = Field(
        description=(
            "True when the active manifest parsed. This does not mean any mechanic is verified."
        )
    )
    recommendations_enabled: bool
