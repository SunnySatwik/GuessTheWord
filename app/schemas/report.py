import datetime as dt
from pydantic import BaseModel, ConfigDict, Field

from app.enums.role import UserRole


class DailyReportResponse(BaseModel):
    """Daily summary report across all player activity."""

    date: dt.date = Field(..., description="Report date in YYYY-MM-DD format (UTC)")
    number_of_users: int = Field(
        ...,
        ge=0,
        description="Number of distinct users who started at least one game on this date",
    )
    number_of_correct_guesses: int = Field(
        ...,
        ge=0,
        description="Number of games won whose session started on this date",
    )

    model_config = ConfigDict(from_attributes=True)


class UserReportResponse(BaseModel):
    """Per-user activity report for a specific date."""

    user_id: int = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    date: dt.date = Field(..., description="Report date in YYYY-MM-DD format (UTC)")
    number_of_words_tried: int = Field(
        ...,
        ge=0,
        description="Number of game sessions started by this user on this date",
    )
    number_of_correct_guesses: int = Field(
        ...,
        ge=0,
        description="Number of games won by this user that started on this date",
    )

    model_config = ConfigDict(from_attributes=True)


class UserSummaryResponse(BaseModel):
    """Minimal user summary for admin selection."""

    id: int = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    role: UserRole = Field(..., description="User role")

    model_config = ConfigDict(from_attributes=True)
