from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain import Position

# Transport ceilings only. In-game minimums and maximums come from verified rules.
Rating = Annotated[int, Field(ge=0, le=150)]
INCH_LIMIT = Field(default=None, ge=1, le=150)
POUND_LIMIT = Field(default=None, ge=1, le=1000)


class LockedPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Position | None = None
    locked: bool = False

    @model_validator(mode="after")
    def lock_needs_value(self) -> "LockedPosition":
        if self.locked and self.value is None:
            raise ValueError("A locked field needs a value.")
        return self


class LockedInches(BaseModel):
    """Inches field. The numeric bound is an API limit, not a legal body range."""

    model_config = ConfigDict(extra="forbid")

    value: int | None = INCH_LIMIT
    locked: bool = False

    @model_validator(mode="after")
    def lock_needs_value(self) -> "LockedInches":
        if self.locked and self.value is None:
            raise ValueError("A locked field needs a value.")
        return self


class LockedPounds(BaseModel):
    """Pounds field. The numeric bound is an API limit, not a legal body range."""

    model_config = ConfigDict(extra="forbid")

    value: int | None = POUND_LIMIT
    locked: bool = False

    @model_validator(mode="after")
    def lock_needs_value(self) -> "LockedPounds":
        if self.locked and self.value is None:
            raise ValueError("A locked field needs a value.")
        return self


class BodyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: LockedPosition = Field(default_factory=LockedPosition)
    height_in: LockedInches = Field(default_factory=LockedInches)
    weight_lb: LockedPounds = Field(default_factory=LockedPounds)
    wingspan_in: LockedInches = Field(default_factory=LockedInches)
