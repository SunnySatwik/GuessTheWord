from datetime import date, datetime, timedelta, timezone
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.enums.game_status import GameStatus
from app.enums.role import UserRole
from app.models.game import Game
from app.models.user import User
from app.models.word import Word
from app.routes.auth import SESSION_COOKIE_NAME
from app.services.auth_service import create_session_token, register_user
from app.services.word_seed import seed_words


# ============================================================================
# Test Fixtures & Helpers
# ============================================================================


@pytest.fixture
def admin_user(db_session: Session) -> User:
    """Create and return a dedicated admin user."""
    return register_user(
        db_session,
        username="adminuser",
        password="AdminPass1$",
        role=UserRole.ADMIN,
    )


@pytest.fixture
def player_user(db_session: Session) -> User:
    """Create and return a standard player user."""
    return register_user(
        db_session,
        username="playerone",
        password="PlayerPass1$",
        role=UserRole.PLAYER,
    )


@pytest.fixture
def second_player(db_session: Session) -> User:
    """Create and return a second player user."""
    return register_user(
        db_session,
        username="playertwo",
        password="PlayerPass2$",
        role=UserRole.PLAYER,
    )


@pytest.fixture
def test_words(db_session: Session) -> list[Word]:
    """Ensure seed words are loaded in the database."""
    return seed_words(db_session)


def set_user_cookie(client: TestClient, user: User) -> None:
    """Helper to set authenticated session cookie on test client."""
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)


def create_game_fixture(
    db: Session,
    user_id: int,
    word_id: int,
    status: GameStatus,
    started_at: datetime,
    completed_at: datetime | None = None,
    attempts: int = 1,
) -> Game:
    """Helper to create a game record with explicit timestamps and status."""
    game = Game(
        user_id=user_id,
        word_id=word_id,
        status=status,
        attempts=attempts,
        started_at=started_at,
        completed_at=completed_at,
    )
    db.add(game)
    db.commit()
    db.refresh(game)
    return game


# ============================================================================
# 1. Authentication & Access Control (RBAC) Tests
# ============================================================================


def test_daily_report_unauthenticated_returns_401(client: TestClient):
    """Verify unauthenticated requests to daily report return HTTP 401."""
    client.cookies.clear()
    response = client.get("/admin/reports/daily")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Authentication required"


def test_daily_report_player_returns_403(client: TestClient, player_user: User):
    """Verify players attempting to access daily report receive HTTP 403."""
    set_user_cookie(client, player_user)
    response = client.get("/admin/reports/daily")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"] == "Insufficient permissions"


def test_daily_report_admin_returns_200(client: TestClient, admin_user: User):
    """Verify admins can access the daily report endpoint."""
    set_user_cookie(client, admin_user)
    response = client.get("/admin/reports/daily?date=2026-09-12")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["date"] == "2026-09-12"
    assert "number_of_users" in data
    assert "number_of_correct_guesses" in data


def test_user_report_unauthenticated_returns_401(client: TestClient, player_user: User):
    """Verify unauthenticated requests to per-user report return HTTP 401."""
    client.cookies.clear()
    response = client.get(f"/admin/reports/user/{player_user.id}")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Authentication required"


def test_user_report_player_returns_403(client: TestClient, player_user: User):
    """Verify players attempting to access per-user report receive HTTP 403."""
    set_user_cookie(client, player_user)
    response = client.get(f"/admin/reports/user/{player_user.id}")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"] == "Insufficient permissions"


def test_user_report_admin_returns_200(
    client: TestClient, admin_user: User, player_user: User
):
    """Verify admins can access the per-user report endpoint."""
    set_user_cookie(client, admin_user)
    response = client.get(f"/admin/reports/user/{player_user.id}?date=2026-09-12")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["user_id"] == player_user.id
    assert data["username"] == player_user.username
    assert data["date"] == "2026-09-12"
    assert "number_of_words_tried" in data
    assert "number_of_correct_guesses" in data


def test_users_list_player_returns_403(client: TestClient, player_user: User):
    """Verify players attempting to access report users list receive HTTP 403."""
    set_user_cookie(client, player_user)
    response = client.get("/admin/reports/users")
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_users_list_admin_returns_200(
    client: TestClient, admin_user: User, player_user: User
):
    """Verify admins can list all users for reporting selection."""
    set_user_cookie(client, admin_user)
    response = client.get("/admin/reports/users")
    assert response.status_code == status.HTTP_200_OK
    users = response.json()
    assert isinstance(users, list)
    usernames = [u["username"] for u in users]
    assert "adminuser" in usernames
    assert "playerone" in usernames


# ============================================================================
# 2. Daily Report Data Accuracy Tests
# ============================================================================


def test_daily_report_empty_date_returns_zeros(client: TestClient, admin_user: User):
    """Verify daily report for a date with no games returns zeros."""
    set_user_cookie(client, admin_user)
    response = client.get("/admin/reports/daily?date=2025-01-01")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["date"] == "2025-01-01"
    assert data["number_of_users"] == 0
    assert data["number_of_correct_guesses"] == 0


def test_daily_report_distinct_users_counted_once_even_with_multiple_games(
    client: TestClient,
    admin_user: User,
    player_user: User,
    second_player: User,
    test_words: list[Word],
    db_session: Session,
):
    """Verify multiple games played by the same user count as 1 user in daily report."""
    set_user_cookie(client, admin_user)
    target_date = date(2026, 6, 15)
    base_time = datetime(2026, 6, 15, 10, 0, 0, tzinfo=timezone.utc)

    # Player 1 starts 3 games on this date
    create_game_fixture(db_session, player_user.id, test_words[0].id, GameStatus.WON, base_time)
    create_game_fixture(db_session, player_user.id, test_words[1].id, GameStatus.LOST, base_time + timedelta(hours=1))
    create_game_fixture(db_session, player_user.id, test_words[2].id, GameStatus.IN_PROGRESS, base_time + timedelta(hours=2))

    # Player 2 starts 1 game on this date
    create_game_fixture(db_session, second_player.id, test_words[3].id, GameStatus.WON, base_time + timedelta(hours=3))

    response = client.get("/admin/reports/daily?date=2026-06-15")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    # Exactly 2 distinct users started games
    assert data["number_of_users"] == 2
    # Exactly 2 games were won (Player 1 game 1 + Player 2 game 1)
    assert data["number_of_correct_guesses"] == 2


def test_daily_report_counts_only_won_as_correct_guesses(
    client: TestClient,
    admin_user: User,
    player_user: User,
    test_words: list[Word],
    db_session: Session,
):
    """Verify LOST and IN_PROGRESS games do not count as correct guesses in daily report."""
    set_user_cookie(client, admin_user)
    base_time = datetime(2026, 7, 20, 14, 0, 0, tzinfo=timezone.utc)

    create_game_fixture(db_session, player_user.id, test_words[0].id, GameStatus.LOST, base_time)
    create_game_fixture(db_session, player_user.id, test_words[1].id, GameStatus.IN_PROGRESS, base_time + timedelta(minutes=30))

    response = client.get("/admin/reports/daily?date=2026-07-20")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["number_of_users"] == 1
    assert data["number_of_correct_guesses"] == 0


def test_daily_report_excludes_games_from_other_dates(
    client: TestClient,
    admin_user: User,
    player_user: User,
    test_words: list[Word],
    db_session: Session,
):
    """Verify games started on different dates are excluded from daily report."""
    set_user_cookie(client, admin_user)

    # Game on July 1
    create_game_fixture(
        db_session, player_user.id, test_words[0].id, GameStatus.WON,
        datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)
    )
    # Game on July 2
    create_game_fixture(
        db_session, player_user.id, test_words[1].id, GameStatus.WON,
        datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc)
    )

    # Query July 1
    res1 = client.get("/admin/reports/daily?date=2026-07-01")
    assert res1.json()["number_of_users"] == 1
    assert res1.json()["number_of_correct_guesses"] == 1

    # Query July 3 (no games)
    res3 = client.get("/admin/reports/daily?date=2026-07-03")
    assert res3.json()["number_of_users"] == 0
    assert res3.json()["number_of_correct_guesses"] == 0


def test_daily_report_started_at_determines_date(
    client: TestClient,
    admin_user: User,
    player_user: User,
    test_words: list[Word],
    db_session: Session,
):
    """Verify game started at 23:55 on day 1 and completed at 00:05 on day 2 is associated with day 1."""
    set_user_cookie(client, admin_user)

    started_at = datetime(2026, 8, 10, 23, 55, 0, tzinfo=timezone.utc)
    completed_at = datetime(2026, 8, 11, 0, 5, 0, tzinfo=timezone.utc)
    create_game_fixture(
        db_session, player_user.id, test_words[0].id, GameStatus.WON,
        started_at=started_at, completed_at=completed_at
    )

    # Day 1 should have the game
    res_day1 = client.get("/admin/reports/daily?date=2026-08-10")
    assert res_day1.json()["number_of_users"] == 1
    assert res_day1.json()["number_of_correct_guesses"] == 1

    # Day 2 should NOT have the game
    res_day2 = client.get("/admin/reports/daily?date=2026-08-11")
    assert res_day2.json()["number_of_users"] == 0
    assert res_day2.json()["number_of_correct_guesses"] == 0


# ============================================================================
# 3. Per-User Report Data Accuracy Tests
# ============================================================================


def test_user_report_words_tried_and_correct_guesses(
    client: TestClient,
    admin_user: User,
    player_user: User,
    test_words: list[Word],
    db_session: Session,
):
    """Verify per-user report accurately counts words tried (games started) and correct guesses (WON)."""
    set_user_cookie(client, admin_user)
    base_time = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)

    # 3 games started: 2 WON, 1 LOST
    create_game_fixture(db_session, player_user.id, test_words[0].id, GameStatus.WON, base_time)
    create_game_fixture(db_session, player_user.id, test_words[1].id, GameStatus.LOST, base_time + timedelta(hours=1))
    create_game_fixture(db_session, player_user.id, test_words[2].id, GameStatus.WON, base_time + timedelta(hours=2))

    response = client.get(f"/admin/reports/user/{player_user.id}?date=2026-09-01")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["user_id"] == player_user.id
    assert data["username"] == "playerone"
    assert data["date"] == "2026-09-01"
    assert data["number_of_words_tried"] == 3
    assert data["number_of_correct_guesses"] == 2


def test_user_report_includes_lost_and_in_progress_in_words_tried(
    client: TestClient,
    admin_user: User,
    player_user: User,
    test_words: list[Word],
    db_session: Session,
):
    """Verify LOST and IN_PROGRESS games count toward words tried but not correct guesses."""
    set_user_cookie(client, admin_user)
    base_time = datetime(2026, 9, 2, 8, 0, 0, tzinfo=timezone.utc)

    create_game_fixture(db_session, player_user.id, test_words[0].id, GameStatus.LOST, base_time)
    create_game_fixture(db_session, player_user.id, test_words[1].id, GameStatus.IN_PROGRESS, base_time + timedelta(hours=1))

    response = client.get(f"/admin/reports/user/{player_user.id}?date=2026-09-02")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["number_of_words_tried"] == 2
    assert data["number_of_correct_guesses"] == 0


def test_user_report_excludes_other_users_games(
    client: TestClient,
    admin_user: User,
    player_user: User,
    second_player: User,
    test_words: list[Word],
    db_session: Session,
):
    """Verify per-user report only counts games started by the requested user."""
    set_user_cookie(client, admin_user)
    base_time = datetime(2026, 9, 3, 11, 0, 0, tzinfo=timezone.utc)

    # Player 1 has 1 game (WON)
    create_game_fixture(db_session, player_user.id, test_words[0].id, GameStatus.WON, base_time)
    # Player 2 has 2 games (both WON)
    create_game_fixture(db_session, second_player.id, test_words[1].id, GameStatus.WON, base_time)
    create_game_fixture(db_session, second_player.id, test_words[2].id, GameStatus.WON, base_time + timedelta(hours=1))

    # Query Player 1
    res1 = client.get(f"/admin/reports/user/{player_user.id}?date=2026-09-03")
    assert res1.json()["number_of_words_tried"] == 1
    assert res1.json()["number_of_correct_guesses"] == 1

    # Query Player 2
    res2 = client.get(f"/admin/reports/user/{second_player.id}?date=2026-09-03")
    assert res2.json()["number_of_words_tried"] == 2
    assert res2.json()["number_of_correct_guesses"] == 2


def test_user_report_excludes_other_dates(
    client: TestClient,
    admin_user: User,
    player_user: User,
    test_words: list[Word],
    db_session: Session,
):
    """Verify per-user report excludes games played on other dates."""
    set_user_cookie(client, admin_user)

    # Game on Sept 4
    create_game_fixture(
        db_session, player_user.id, test_words[0].id, GameStatus.WON,
        datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
    )

    # Query Sept 5 (empty date for this user)
    response = client.get(f"/admin/reports/user/{player_user.id}?date=2026-09-05")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["number_of_words_tried"] == 0
    assert data["number_of_correct_guesses"] == 0


def test_user_report_zero_activity_date_returns_zeros(
    client: TestClient, admin_user: User, player_user: User
):
    """Verify zero activity on a date returns valid report with 0 words tried and 0 correct guesses."""
    set_user_cookie(client, admin_user)
    response = client.get(f"/admin/reports/user/{player_user.id}?date=2025-05-05")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["number_of_words_tried"] == 0
    assert data["number_of_correct_guesses"] == 0


def test_user_report_nonexistent_user_returns_404(
    client: TestClient, admin_user: User
):
    """Verify requesting a report for a nonexistent user ID returns HTTP 404."""
    set_user_cookie(client, admin_user)
    response = client.get("/admin/reports/user/999999?date=2026-09-12")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in response.json()["detail"].lower()


# ============================================================================
# 4. Date Parsing & Parameter Edge Cases Tests
# ============================================================================


def test_daily_report_defaults_to_today_when_date_omitted(
    client: TestClient,
    admin_user: User,
    player_user: User,
    test_words: list[Word],
    db_session: Session,
):
    """Verify omitting date defaults to current UTC date."""
    set_user_cookie(client, admin_user)
    today_utc = datetime.now(timezone.utc)

    # Game started today
    create_game_fixture(
        db_session, player_user.id, test_words[0].id, GameStatus.WON,
        today_utc
    )

    response = client.get("/admin/reports/daily")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["date"] == str(today_utc.date())
    assert data["number_of_users"] == 1
    assert data["number_of_correct_guesses"] == 1


def test_user_report_defaults_to_today_when_date_omitted(
    client: TestClient,
    admin_user: User,
    player_user: User,
    test_words: list[Word],
    db_session: Session,
):
    """Verify omitting date in user report defaults to current UTC date."""
    set_user_cookie(client, admin_user)
    today_utc = datetime.now(timezone.utc)

    create_game_fixture(
        db_session, player_user.id, test_words[0].id, GameStatus.WON,
        today_utc
    )

    response = client.get(f"/admin/reports/user/{player_user.id}")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["date"] == str(today_utc.date())
    assert data["number_of_words_tried"] == 1
    assert data["number_of_correct_guesses"] == 1


def test_daily_report_invalid_date_format_returns_422(
    client: TestClient, admin_user: User
):
    """Verify passing an invalid date format returns HTTP 422 validation error."""
    set_user_cookie(client, admin_user)
    response = client.get("/admin/reports/daily?date=invalid-date")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_user_report_invalid_date_format_returns_422(
    client: TestClient, admin_user: User, player_user: User
):
    """Verify passing an invalid date format to user report returns HTTP 422."""
    set_user_cookie(client, admin_user)
    response = client.get(f"/admin/reports/user/{player_user.id}?date=not-a-date")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ============================================================================
# 5. Phase 4C-2 Admin Reports UI Foundation & Navigation Tests
# ============================================================================


def test_admin_reports_html_unauthenticated_redirects_to_login(client: TestClient):
    """Verify unauthenticated requests to /admin/reports redirect to /login with 303."""
    client.cookies.clear()
    response = client.get("/admin/reports", follow_redirects=False)
    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert response.headers["location"] == "/login"


def test_admin_reports_html_player_returns_403(client: TestClient, player_user: User):
    """Verify authenticated PLAYER user visiting /admin/reports receives HTTP 403."""
    set_user_cookie(client, player_user)
    response = client.get("/admin/reports", follow_redirects=False)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"] == "Insufficient permissions"


def test_admin_reports_html_admin_returns_200(client: TestClient, admin_user: User):
    """Verify authenticated ADMIN user visiting /admin/reports receives HTML dashboard."""
    set_user_cookie(client, admin_user)
    response = client.get("/admin/reports")
    assert response.status_code == status.HTTP_200_OK
    assert "text/html" in response.headers["content-type"]
    html = response.text

    assert "Admin Reports" in html
    assert 'id="daily-report-section"' in html
    assert 'id="daily-report-form"' in html
    assert 'id="report-date-input"' in html
    assert 'id="btn-run-daily-report"' in html
    assert 'id="metric-users-value"' in html
    assert 'id="metric-correct-value"' in html
    assert 'id="context-date-display"' in html
    assert 'id="report-feedback"' in html
    assert "admin.css" in html
    assert "admin.js" in html


def test_admin_navigation_visible_for_admin_user(client: TestClient, admin_user: User):
    """Verify Admin Reports navigation link is rendered in navbar for ADMIN users."""
    set_user_cookie(client, admin_user)
    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    html = response.text
    assert 'href="/admin/reports"' in html
    assert "Admin Reports" in html


def test_admin_navigation_absent_for_player_user(client: TestClient, player_user: User):
    """Verify Admin Reports navigation link is NOT rendered for PLAYER users."""
    set_user_cookie(client, player_user)
    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    html = response.text
    assert 'href="/admin/reports"' not in html
    assert "Admin Reports" not in html
    # Player navigation still intact
    assert 'href="/game"' in html
    assert "Play Game" in html


def test_admin_navigation_absent_for_unauthenticated_user(client: TestClient):
    """Verify Admin Reports navigation link is NOT rendered for guests."""
    client.cookies.clear()
    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    html = response.text
    assert 'href="/admin/reports"' not in html
    assert "Admin Reports" not in html


def test_admin_static_assets_served(client: TestClient):
    """Verify admin.css and admin.js are served properly."""
    css_res = client.get("/static/css/admin.css")
    assert css_res.status_code == status.HTTP_200_OK
    assert ".admin-page-container" in css_res.text
    assert ".metrics-grid" in css_res.text
    assert ".btn-run-report" in css_res.text

    js_res = client.get("/static/js/admin.js")
    assert js_res.status_code == status.HTTP_200_OK
    assert "window.GuessTheWord.AdminReports" in js_res.text
    assert "fetchDailyReport" in js_res.text
    assert "setLoading" in js_res.text


# ============================================================================
# 6. Phase 4C-3 Per-User Report UI Tests
# ============================================================================


def test_user_report_section_and_elements_exist_in_admin_reports_html(
    client: TestClient, admin_user: User
):
    """Verify Per-User Report section, controls, and metric cards exist in rendered HTML."""
    set_user_cookie(client, admin_user)
    response = client.get("/admin/reports")
    assert response.status_code == status.HTTP_200_OK
    html = response.text

    # Section and heading
    assert 'id="user-report-section"' in html
    assert 'id="user-report-heading"' in html
    assert "User Activity Report" in html

    # Controls and form
    assert 'id="user-report-form"' in html
    assert 'id="user-select"' in html
    assert 'id="user-report-date-input"' in html
    assert 'id="btn-run-user-report"' in html

    # Feedback and Context
    assert 'id="user-report-feedback"' in html
    assert 'id="user-context-bar"' in html
    assert 'id="user-context-username"' in html
    assert 'id="user-context-date"' in html

    # Metric cards
    assert 'id="metric-card-words-tried"' in html
    assert 'id="metric-words-tried-value"' in html
    assert 'id="metric-card-user-correct"' in html
    assert 'id="metric-user-correct-value"' in html


def test_user_report_accessible_labels_and_attributes(
    client: TestClient, admin_user: User
):
    """Verify accessible labels and ARIA attributes for User Report controls."""
    set_user_cookie(client, admin_user)
    response = client.get("/admin/reports")
    assert response.status_code == status.HTTP_200_OK
    html = response.text

    assert 'for="user-select"' in html
    assert 'for="user-report-date-input"' in html
    assert 'aria-live="polite"' in html
    assert 'role="status"' in html


def test_user_report_static_assets_contain_user_report_logic(client: TestClient):
    """Verify static assets contain complete Phase 4C-3 client-side logic and styles."""
    js_res = client.get("/static/js/admin.js")
    assert js_res.status_code == status.HTTP_200_OK
    js_text = js_res.text

    assert "loadUsers" in js_text
    assert "populateUserSelect" in js_text
    assert "fetchUserReport" in js_text
    assert "renderUserReport" in js_text
    assert "userReportRequestId" in js_text
    assert "user-select" in js_text
    assert "metric-words-tried-value" in js_text
    assert "metric-user-correct-value" in js_text

    css_res = client.get("/static/css/admin.css")
    assert css_res.status_code == status.HTTP_200_OK
    css_text = css_res.text

    assert ".control-select" in css_text
    assert ".context-user" in css_text
    assert ".context-separator" in css_text
    assert ".metric-card-words-tried" in css_text
    assert ".metric-card-user-correct" in css_text
