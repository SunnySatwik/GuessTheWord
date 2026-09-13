from datetime import date, datetime, timedelta, timezone
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.enums.game_status import GameStatus
from app.exceptions import UserNotFoundError
from app.models.game import Game
from app.models.user import User
from app.schemas.report import (
    DailyReportResponse,
    UserReportResponse,
    UserSummaryResponse,
)


def get_daily_report(db: Session, target_date: date) -> DailyReportResponse:
    """Generate daily aggregate report across all players for a given calendar date.

    - Number of users: distinct players who started at least one game on target_date (UTC).
    - Number of correct guesses: games won whose session started on target_date (UTC).
    """
    day_start = datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        0,
        0,
        0,
        tzinfo=timezone.utc,
    )
    day_end = day_start + timedelta(days=1)

    stmt = select(
        func.count(func.distinct(Game.user_id)).label("number_of_users"),
        func.count(case((Game.status == GameStatus.WON, 1), else_=None)).label(
            "number_of_correct_guesses"
        ),
    ).where(
        Game.started_at >= day_start,
        Game.started_at < day_end,
    )

    row = db.execute(stmt).one()

    return DailyReportResponse(
        date=target_date,
        number_of_users=row.number_of_users or 0,
        number_of_correct_guesses=row.number_of_correct_guesses or 0,
    )


def get_user_report(db: Session, user_id: int, target_date: date) -> UserReportResponse:
    """Generate per-user activity report for a specific player on a given calendar date.

    - Words tried: game sessions started by user_id on target_date (UTC).
    - Correct guesses: games won by user_id whose session started on target_date (UTC).

    Raises UserNotFoundError if user_id does not exist.
    """
    user = db.get(User, user_id)
    if not user:
        raise UserNotFoundError(f"User with ID {user_id} not found.")

    day_start = datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        0,
        0,
        0,
        tzinfo=timezone.utc,
    )
    day_end = day_start + timedelta(days=1)

    stmt = select(
        func.count(Game.id).label("number_of_words_tried"),
        func.count(case((Game.status == GameStatus.WON, 1), else_=None)).label(
            "number_of_correct_guesses"
        ),
    ).where(
        Game.user_id == user_id,
        Game.started_at >= day_start,
        Game.started_at < day_end,
    )

    row = db.execute(stmt).one()

    return UserReportResponse(
        user_id=user.id,
        username=user.username,
        date=target_date,
        number_of_words_tried=row.number_of_words_tried or 0,
        number_of_correct_guesses=row.number_of_correct_guesses or 0,
    )


def list_report_users(db: Session) -> list[UserSummaryResponse]:
    """List all registered users ordered by username for admin reporting selection."""
    stmt = select(User).order_by(User.username)
    users = db.execute(stmt).scalars().all()
    return [
        UserSummaryResponse(id=u.id, username=u.username, role=u.role)
        for u in users
    ]
