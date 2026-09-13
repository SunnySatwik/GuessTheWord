import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.create_admin import run_create_admin
from app.enums.role import UserRole
from app.models.user import User
from app.routes.auth import SESSION_COOKIE_NAME
from app.services.auth_service import (
    create_admin_account,
    create_session_token,
    get_user_by_username,
    verify_password,
)


# ============================================================================
# 1. Admin Provisioning Unit Tests
# ============================================================================


def test_create_admin_account_success(db_session: Session):
    """Verify create_admin_account creates a user in the database."""
    admin = create_admin_account(
        db=db_session,
        username="superadmin",
        password="SuperPass1$",
        confirm_password="SuperPass1$",
    )
    assert admin is not None
    assert admin.id is not None
    assert admin.username == "superadmin"

    # Query from DB to confirm persistence
    fetched = db_session.get(User, admin.id)
    assert fetched is not None
    assert fetched.username == "superadmin"


def test_create_admin_role_is_admin(db_session: Session):
    """Verify provisioned account has UserRole.ADMIN role."""
    admin = create_admin_account(
        db=db_session,
        username="adminlead",
        password="AdminLead1*",
        confirm_password="AdminLead1*",
    )
    assert admin.role == UserRole.ADMIN
    assert admin.role.value == "ADMIN"


def test_create_admin_password_stored_as_hash_not_plaintext(db_session: Session):
    """Verify password is stored as Argon2id hash and plaintext is never persisted."""
    raw_password = "SecureAdmin1%"
    admin = create_admin_account(
        db=db_session,
        username="hashadmin",
        password=raw_password,
        confirm_password=raw_password,
    )

    # Password hash must NOT equal plaintext
    assert admin.password_hash != raw_password
    # Must be valid Argon2id hash format
    assert admin.password_hash.startswith("$argon2id$")
    # Must successfully verify against plain password
    assert verify_password(raw_password, admin.password_hash) is True
    # Must fail verification against incorrect password
    assert verify_password("WrongPassword1$", admin.password_hash) is False
    # User model must not have any plaintext password attribute
    assert not hasattr(admin, "password")


def test_create_admin_username_normalized(db_session: Session):
    """Verify username is trimmed and converted to lowercase."""
    admin = create_admin_account(
        db=db_session,
        username="  MixedAdmin  ",
        password="ValidPass1$",
        confirm_password="ValidPass1$",
    )
    assert admin.username == "mixedadmin"


def test_create_admin_invalid_username_rejected(db_session: Session):
    """Verify short or invalid usernames are rejected with ValueError."""
    # Under 5 characters
    with pytest.raises(ValueError, match="at least 5 characters"):
        create_admin_account(
            db=db_session,
            username="adm",
            password="ValidPass1$",
            confirm_password="ValidPass1$",
        )

    # Empty username
    with pytest.raises(ValueError, match="at least 5 characters"):
        create_admin_account(
            db=db_session,
            username="   ",
            password="ValidPass1$",
            confirm_password="ValidPass1$",
        )

    # Non-alphabetic username (digits)
    with pytest.raises(ValueError, match="only alphabetic letters"):
        create_admin_account(
            db=db_session,
            username="admin123",
            password="ValidPass1$",
            confirm_password="ValidPass1$",
        )

    # Non-alphabetic username (symbols)
    with pytest.raises(ValueError, match="only alphabetic letters"):
        create_admin_account(
            db=db_session,
            username="admin_lead",
            password="ValidPass1$",
            confirm_password="ValidPass1$",
        )


def test_create_admin_invalid_password_rejected(db_session: Session):
    """Verify passwords failing complexity requirements are rejected with ValueError."""
    # Short password (< 5 characters)
    with pytest.raises(ValueError, match="at least 5 characters"):
        create_admin_account(db_session, "validadmin", "Ab1$", "Ab1$")

    # Missing letters
    with pytest.raises(ValueError, match="alphabetic character"):
        create_admin_account(db_session, "validadmin", "123456$*", "123456$*")

    # Missing numbers
    with pytest.raises(ValueError, match="numeric character"):
        create_admin_account(db_session, "validadmin", "AdminPass$", "AdminPass$")

    # Missing special character (must have $, %, or *)
    with pytest.raises(ValueError, match=r"\$, %, \*"):
        create_admin_account(db_session, "validadmin", "AdminPass12", "AdminPass12")

    # Disallowed special character (! instead of $, %, *)
    with pytest.raises(ValueError, match=r"\$, %, \*"):
        create_admin_account(db_session, "validadmin", "AdminPass1!", "AdminPass1!")


def test_create_admin_mismatched_confirm_password_rejected(db_session: Session):
    """Verify mismatched password confirmation is rejected."""
    with pytest.raises(ValueError, match="Passwords do not match"):
        create_admin_account(
            db=db_session,
            username="validadmin",
            password="CorrectPass1$",
            confirm_password="DifferentPass1$",
        )


def test_create_admin_duplicate_username_rejected(db_session: Session):
    """Verify duplicate username raises ValueError cleanly."""
    create_admin_account(
        db=db_session,
        username="existingadmin",
        password="FirstPass1$",
        confirm_password="FirstPass1$",
    )

    with pytest.raises(ValueError, match="already taken"):
        create_admin_account(
            db=db_session,
            username="existingadmin",
            password="SecondPass1$",
            confirm_password="SecondPass1$",
        )


# ============================================================================
# 2. CLI Provisioning Flow & Error Handling
# ============================================================================


def test_run_create_admin_cli_success(db_session: Session, capsys):
    """Verify run_create_admin returns 0 and prints success message."""
    exit_code = run_create_admin(
        db=db_session,
        username_input="cliadmin",
        password_input="CliPass1$",
        confirm_input="CliPass1$",
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Success: Admin account 'cliadmin' created successfully." in captured.out
    assert get_user_by_username(db_session, "cliadmin") is not None


def test_run_create_admin_cli_duplicate_returns_exit_code_1(db_session: Session, capsys):
    """Verify run_create_admin returns 1 and prints clean error on duplicate without traceback."""
    create_admin_account(
        db=db_session,
        username="dupeadmin",
        password="FirstPass1$",
        confirm_password="FirstPass1$",
    )

    exit_code = run_create_admin(
        db=db_session,
        username_input="dupeadmin",
        password_input="SecondPass1$",
        confirm_input="SecondPass1$",
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Error: Username 'dupeadmin' is already taken." in captured.err
    assert "Traceback" not in captured.err


def test_run_create_admin_cli_validation_failure_returns_exit_code_1(db_session: Session, capsys):
    """Verify run_create_admin returns 1 on validation error."""
    exit_code = run_create_admin(
        db=db_session,
        username_input="short",
        password_input="no_numbers_or_specials",
        confirm_input="no_numbers_or_specials",
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Error:" in captured.err


def test_run_create_admin_interactive_inputs(db_session: Session, monkeypatch, capsys):
    """Verify run_create_admin prompts interactively via input() and getpass.getpass()."""
    inputs = ["interactiveadmin"]
    passwords = ["InteractivePass1$", "InteractivePass1$"]

    monkeypatch.setattr("builtins.input", lambda prompt="": inputs.pop(0))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": passwords.pop(0))

    exit_code = run_create_admin(db=db_session)
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Success: Admin account 'interactiveadmin' created successfully." in captured.out


# ============================================================================
# 3. Registration Security Tests (Role Injection Prevention)
# ============================================================================


def test_public_registration_creates_player_role(client: TestClient, db_session: Session):
    """Verify normal registration always creates a user with PLAYER role."""
    response = client.post(
        "/register",
        json={"username": "normalplayer", "password": "PlayerPass1$"},
    )
    assert response.status_code == status.HTTP_201_CREATED

    user = get_user_by_username(db_session, "normalplayer")
    assert user is not None
    assert user.role == UserRole.PLAYER


def test_public_registration_cannot_create_admin_via_injected_role_json(
    client: TestClient, db_session: Session
):
    """Verify public registration ignores role field injected in JSON payload."""
    response = client.post(
        "/register",
        json={
            "username": "attackerjson",
            "password": "AttackPass1$",
            "role": "ADMIN",
        },
    )
    assert response.status_code == status.HTTP_201_CREATED

    user = get_user_by_username(db_session, "attackerjson")
    assert user is not None
    # Must STILL be PLAYER, never ADMIN
    assert user.role == UserRole.PLAYER
    assert user.role != UserRole.ADMIN


def test_public_registration_cannot_create_admin_via_injected_role_form(
    client: TestClient, db_session: Session
):
    """Verify public registration ignores role field injected in form data."""
    response = client.post(
        "/register",
        data={
            "username": "attackerform",
            "password": "AttackPass1$",
            "role": "ADMIN",
        },
        follow_redirects=False,
    )
    assert response.status_code == status.HTTP_303_SEE_OTHER

    user = get_user_by_username(db_session, "attackerform")
    assert user is not None
    # Must STILL be PLAYER, never ADMIN
    assert user.role == UserRole.PLAYER
    assert user.role != UserRole.ADMIN


# ============================================================================
# 4. Authentication & Authorization of Provisioned Admin
# ============================================================================


def test_provisioned_admin_can_authenticate_using_normal_login(
    client: TestClient, db_session: Session
):
    """Verify provisioned admin account can log in via standard /login endpoint."""
    raw_pass = "LoginAdminPass1$"
    create_admin_account(
        db=db_session,
        username="loginadmin",
        password=raw_pass,
        confirm_password=raw_pass,
    )

    response = client.post(
        "/login",
        data={"username": "loginadmin", "password": raw_pass},
        follow_redirects=False,
    )
    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert SESSION_COOKIE_NAME in response.cookies


def test_provisioned_admin_can_access_admin_reports(
    client: TestClient, db_session: Session
):
    """Verify provisioned admin can access protected /admin/reports HTML dashboard."""
    raw_pass = "ReportAdmin1$"
    admin = create_admin_account(
        db=db_session,
        username="reportadmin",
        password=raw_pass,
        confirm_password=raw_pass,
    )

    token = create_session_token(admin.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    response = client.get("/admin/reports")
    assert response.status_code == status.HTTP_200_OK
    assert "Admin Reports" in response.text
    assert "User Activity Report" in response.text


def test_player_cannot_access_admin_reports(client: TestClient, db_session: Session):
    """Verify standard player user receives HTTP 403 Forbidden on /admin/reports."""
    # Register a standard player
    client.post(
        "/register",
        json={"username": "regularplayer", "password": "RegularPass1$"},
    )
    player = get_user_by_username(db_session, "regularplayer")
    assert player.role == UserRole.PLAYER

    token = create_session_token(player.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    response = client.get("/admin/reports")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"] == "Insufficient permissions"
