from datetime import datetime, timedelta, timezone
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.enums.game_status import GameStatus
from app.exceptions import DailyLimitReachedError
from app.models.game import Game
from app.models.word import Word
from app.routes.auth import SESSION_COOKIE_NAME
from app.services.auth_service import create_session_token, register_user
from app.services.game_service import (
    count_daily_games,
    start_game,
)
from app.services.word_seed import seed_words


def test_count_daily_games_accurate(db_session: Session):
    """Verify count_daily_games only counts sessions started today (UTC)."""
    seed_words(db_session)
    user = register_user(db_session, username="dailyuser1", password="Password1$")
    word = db_session.query(Word).first()

    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)

    # 1 game yesterday
    game_yesterday = Game(
        user_id=user.id,
        word_id=word.id,
        status=GameStatus.IN_PROGRESS,
        started_at=yesterday,
    )
    # 2 games today
    game_today1 = Game(
        user_id=user.id,
        word_id=word.id,
        status=GameStatus.IN_PROGRESS,
        started_at=now,
    )
    game_today2 = Game(
        user_id=user.id,
        word_id=word.id,
        status=GameStatus.IN_PROGRESS,
        started_at=now,
    )
    db_session.add_all([game_yesterday, game_today1, game_today2])
    db_session.commit()

    # Today should count 2
    assert count_daily_games(db_session, user.id) == 2


def test_player_can_start_up_to_three_games_today(db_session: Session):
    """Verify player can start exactly 3 games on the same day."""
    seed_words(db_session)
    user = register_user(db_session, username="threegamesplayer", password="Password1$")

    # Start 3 games
    g1 = start_game(db_session, user.id)
    g2 = start_game(db_session, user.id)
    g3 = start_game(db_session, user.id)

    assert g1.id is not None
    assert g2.id is not None
    assert g3.id is not None
    assert count_daily_games(db_session, user.id) == 3


def test_fourth_game_on_same_day_rejected(db_session: Session):
    """Verify attempting to start a 4th game on the same day raises DailyLimitReachedError."""
    seed_words(db_session)
    user = register_user(db_session, username="fourthgamereject", password="Password1$")

    # Start 3 games
    for _ in range(3):
        start_game(db_session, user.id)

    # 4th game must raise DailyLimitReachedError
    with pytest.raises(DailyLimitReachedError) as exc_info:
        start_game(db_session, user.id)

    assert "Daily limit reached" in str(exc_info.value)


def test_games_from_different_day_do_not_count_toward_today(db_session: Session):
    """Verify games started on past days do not block today's 3 allowed games."""
    seed_words(db_session)
    user = register_user(db_session, username="pastdaygamesuser", password="Password1$")
    word = db_session.query(Word).first()

    past_date = datetime.now(timezone.utc) - timedelta(days=2)

    # Add 3 games from 2 days ago
    for _ in range(3):
        g = Game(
            user_id=user.id,
            word_id=word.id,
            status=GameStatus.WON,
            started_at=past_date,
            completed_at=past_date,
        )
        db_session.add(g)
    db_session.commit()

    # Player should still be able to start 3 games today
    g1 = start_game(db_session, user.id)
    g2 = start_game(db_session, user.id)
    g3 = start_game(db_session, user.id)

    assert g1.id is not None
    assert g2.id is not None
    assert g3.id is not None
    assert count_daily_games(db_session, user.id) == 3


def test_different_players_have_independent_daily_limits(db_session: Session):
    """Verify player A reaching 3 games does not affect player B."""
    seed_words(db_session)
    user_a = register_user(db_session, username="playeraaa", password="Password1$")
    user_b = register_user(db_session, username="playerbbb", password="Password1$")

    # Player A starts 3 games
    for _ in range(3):
        start_game(db_session, user_a.id)

    # Player A is blocked
    with pytest.raises(DailyLimitReachedError):
        start_game(db_session, user_a.id)

    # Player B can still start games
    game_b = start_game(db_session, user_b.id)
    assert game_b.id is not None
    assert game_b.user_id == user_b.id


def test_api_daily_limit_returns_429(client: TestClient, db_session: Session):
    """Verify /game/start endpoint returns HTTP 429 when daily limit is exceeded."""
    seed_words(db_session)
    user = register_user(db_session, username="apilimitplayer", password="Password1$")
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    # Start 3 games
    for _ in range(3):
        res = client.post("/game/start")
        assert res.status_code == status.HTTP_201_CREATED

    # 4th game must return 429 Too Many Requests
    fourth_res = client.post("/game/start")
    assert fourth_res.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert "Daily limit reached" in fourth_res.json()["detail"]
