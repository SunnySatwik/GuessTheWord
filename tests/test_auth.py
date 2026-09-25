import pytest
from fastapi import Depends, HTTPException, status
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.enums.role import UserRole
from app.main import app
from app.models.user import User
from app.schemas.auth import UserRegisterSchema
from app.routes.auth import (
    SESSION_COOKIE_NAME,
    get_current_user,
    require_authenticated_user,
    require_role,
)
from app.services.auth_service import (
    authenticate_user,
    create_session_token,
    get_user_by_username,
    register_user,
    verify_password,
)

# Attach test routes for dependency verification
@app.get("/test-protected-route")
def _protected_route(user: User = Depends(require_authenticated_user)):
    return {"message": "ok", "username": user.username}


@app.get("/test-admin-route")
def _admin_route(user: User = Depends(require_role(UserRole.ADMIN))):
    return {"message": "ok", "admin": user.username}


# ============================================================================
# 1. Registration Tests
# ============================================================================


def test_valid_registration_succeeds(client: TestClient, db_session: Session):
    """Verify valid registration redirects to /login?registered=1 and stores user with PLAYER role."""
    response = client.post(
        "/register",
        data={
            "username": "playeralice",
            "password": "Password1$",
            "confirm_password": "Password1$",
        },
        follow_redirects=False,
    )
    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert response.headers["location"] == "/login?registered=1"

    user = get_user_by_username(db_session, "playeralice")
    assert user is not None
    assert user.username == "playeralice"
    assert user.role == UserRole.PLAYER
    assert user.created_at is not None


def test_registration_page_renders_confirm_password_field(client: TestClient):
    """Verify registration page renders password and confirm_password inputs with required attributes."""
    response = client.get("/register")
    assert response.status_code == status.HTTP_200_OK
    html = response.text
    assert 'id="confirm_password"' in html
    assert 'name="confirm_password"' in html
    assert 'type="password"' in html
    assert 'autocomplete="new-password"' in html
    assert 'for="confirm_password"' in html
    assert "Confirm Password" in html


def test_registration_matching_passwords_succeeds_json(
    client: TestClient, db_session: Session
):
    """Verify JSON registration with matching passwords succeeds with HTTP 201."""
    response = client.post(
        "/register",
        json={
            "username": "jsonmatchuser",
            "password": "Password1$",
            "confirm_password": "Password1$",
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["username"] == "jsonmatchuser"

    user = get_user_by_username(db_session, "jsonmatchuser")
    assert user is not None
    assert user.role == UserRole.PLAYER


def test_registration_non_matching_passwords_rejected_form(client: TestClient):
    """Verify form registration with non-matching passwords is rejected with HTTP 400."""
    response = client.post(
        "/register",
        data={
            "username": "mismatchplayer",
            "password": "Password1$",
            "confirm_password": "DifferentPassword1%",
        },
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Passwords do not match." in response.text
    # Username preserved in input value
    assert 'value="mismatchplayer"' in response.text
    # Plaintext password is never echoed back in the response
    assert "Password1$" not in response.text
    assert "DifferentPassword1%" not in response.text


def test_registration_non_matching_passwords_rejected_json(client: TestClient):
    """Verify JSON registration with non-matching passwords is rejected with HTTP 400."""
    response = client.post(
        "/register",
        json={
            "username": "mismatchjson",
            "password": "Password1$",
            "confirm_password": "DifferentPassword1%",
        },
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "Passwords do not match."


def test_registration_empty_confirm_password_rejected(client: TestClient):
    """Verify registration fails when confirm_password is empty string."""
    response = client.post(
        "/register",
        data={
            "username": "emptyconfirm",
            "password": "Password1$",
            "confirm_password": "",
        },
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Passwords do not match." in response.text


def test_register_user_service_password_mismatch_raises(db_session: Session):
    """Verify register_user service function raises ValueError when confirm_password does not match."""
    with pytest.raises(ValueError, match="Passwords do not match."):
        register_user(
            db_session,
            username="servicefailuser",
            password="Password1$",
            confirm_password="MismatchPassword1$",
        )


def test_user_register_schema_validation():
    """Verify UserRegisterSchema validates password matching."""
    # Matching succeeds
    schema = UserRegisterSchema(
        username="validuser",
        password="Password1$",
        confirm_password="Password1$",
    )
    assert schema.username == "validuser"

    # Mismatch raises ValidationError
    with pytest.raises(ValidationError) as exc_info:
        UserRegisterSchema(
            username="validuser",
            password="Password1$",
            confirm_password="MismatchPassword1$",
        )
    assert "Passwords do not match." in str(exc_info.value)


def test_username_shorter_than_required_fails(client: TestClient):
    """Verify registration fails when username has fewer than 5 characters."""
    response = client.post(
        "/register",
        data={"username": "four", "password": "Password1$"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Username must be at least 5 characters long." in response.text


def test_password_shorter_than_required_fails(client: TestClient):
    """Verify registration fails when password has fewer than 5 characters."""
    response = client.post(
        "/register",
        data={"username": "validuser", "password": "P1$"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Password must be at least 5 characters long." in response.text


def test_password_missing_alphabetic_fails(client: TestClient):
    """Verify registration fails when password lacks alphabetic characters."""
    response = client.post(
        "/register",
        data={"username": "validuser", "password": "12345$"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Password must contain at least one alphabetic character." in response.text


def test_password_missing_numeric_fails(client: TestClient):
    """Verify registration fails when password lacks numeric characters."""
    response = client.post(
        "/register",
        data={"username": "validuser", "password": "Password$"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Password must contain at least one numeric character." in response.text


def test_password_missing_required_special_character_fails(client: TestClient):
    """Verify registration fails when password lacks at least one of $, %, *."""
    # Exclamation mark is special, but NOT one of $, %, *
    response = client.post(
        "/register",
        data={"username": "validuser", "password": "Password1!"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "special characters: $, %, *" in response.text

    # Verify each allowed special character succeeds
    char_labels = {"$": "dollar", "%": "percent", "*": "asterisk"}
    for allowed_char, label in char_labels.items():
        u_name = f"userwith{label}"
        res = client.post(
            "/register",
            data={"username": u_name, "password": f"Password1{allowed_char}"},
            follow_redirects=False,
        )
        assert res.status_code == status.HTTP_303_SEE_OTHER


def test_username_with_non_alphabetic_characters_fails(client: TestClient):
    """Verify registration fails when username contains non-alphabetic characters."""
    # Digits in username
    res_digits = client.post(
        "/register",
        data={"username": "player1", "password": "Password1$"},
    )
    assert res_digits.status_code == status.HTTP_400_BAD_REQUEST
    assert "Username must contain only alphabetic letters." in res_digits.text

    # Underscores / punctuation in username
    res_punct = client.post(
        "/register",
        data={"username": "user_test", "password": "Password1$"},
    )
    assert res_punct.status_code == status.HTTP_400_BAD_REQUEST
    assert "Username must contain only alphabetic letters." in res_punct.text


def test_username_with_mixed_case_letters_normalizes(client: TestClient, db_session: Session):
    """Verify usernames with mixed uppercase and lowercase letters succeed and normalize."""
    res = client.post(
        "/register",
        data={"username": "AliceWonder", "password": "Password1$"},
        follow_redirects=False,
    )
    assert res.status_code == status.HTTP_303_SEE_OTHER
    user = get_user_by_username(db_session, "alicewonder")
    assert user is not None
    assert user.username == "alicewonder"


def test_duplicate_username_rejected(client: TestClient, db_session: Session):
    """Verify duplicate username registration is rejected with appropriate error."""
    register_user(db_session, username="duplicateuser", password="Password1$")

    response = client.post(
        "/register",
        data={"username": "DuplicateUser", "password": "Password2%"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Username is already taken." in response.text


def test_password_stored_as_hash_never_plaintext(client: TestClient, db_session: Session):
    """Verify password is saved as Argon2 hash and plaintext is never stored."""
    raw_password = "SecretPassword1*"
    client.post(
        "/register",
        data={"username": "hasheyuser", "password": raw_password},
    )

    user = get_user_by_username(db_session, "hasheyuser")
    assert user is not None
    assert user.password_hash != raw_password
    assert raw_password not in user.password_hash
    assert user.password_hash.startswith("$argon2id$")
    assert verify_password(raw_password, user.password_hash) is True


# ============================================================================
# 2. Login & Session Tests
# ============================================================================


def test_login_with_correct_credentials_succeeds(client: TestClient, db_session: Session):
    """Verify login sets session cookie and redirects to /."""
    register_user(db_session, username="loginplayer", password="Password1$")

    response = client.post(
        "/login",
        data={"username": "loginplayer", "password": "Password1$"},
        follow_redirects=False,
    )
    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert response.headers["location"] == "/"
    assert SESSION_COOKIE_NAME in response.cookies


def test_login_with_incorrect_password_fails(client: TestClient, db_session: Session):
    """Verify login with incorrect password shows generic error message."""
    register_user(db_session, username="playerwrongpass", password="Password1$")

    response = client.post(
        "/login",
        data={"username": "playerwrongpass", "password": "WrongPassword1$"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid username or password." in response.text
    assert SESSION_COOKIE_NAME not in client.cookies


def test_login_with_nonexistent_username_fails(client: TestClient):
    """Verify login with non-existent username shows safe generic error message."""
    response = client.post(
        "/login",
        data={"username": "ghostuser", "password": "Password1$"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid username or password." in response.text
    assert SESSION_COOKIE_NAME not in client.cookies


def test_authenticated_session_identifies_correct_user(client: TestClient, db_session: Session):
    """Verify authenticated session correctly identifies user on protected routes and home."""
    user = register_user(db_session, username="sessiontester", password="Password1$")
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    # 1. Root page shows username
    home_res = client.get("/")
    assert home_res.status_code == status.HTTP_200_OK
    assert "sessiontester" in home_res.text

    # 2. Protected helper identifies user
    prot_res = client.get("/test-protected-route")
    assert prot_res.status_code == status.HTTP_200_OK
    assert prot_res.json()["username"] == "sessiontester"


def test_logout_removes_authentication(client: TestClient, db_session: Session):
    """Verify logout deletes session cookie and revokes authentication."""
    register_user(db_session, username="logoutuser", password="Password1$")

    # Login via endpoint
    login_res = client.post(
        "/login",
        data={"username": "logoutuser", "password": "Password1$"},
        follow_redirects=False,
    )
    assert login_res.status_code == status.HTTP_303_SEE_OTHER
    assert SESSION_COOKIE_NAME in client.cookies

    # Verify active session on protected route
    assert client.get("/test-protected-route").status_code == status.HTTP_200_OK

    # Logout
    logout_res = client.post("/logout", follow_redirects=False)
    assert logout_res.status_code == status.HTTP_303_SEE_OTHER
    assert logout_res.headers["location"] == "/login"

    # Protected route should now be rejected
    after_logout_res = client.get("/test-protected-route")
    assert after_logout_res.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# 3. Protected Route & Role-Based Access Tests
# ============================================================================


def test_unauthenticated_access_rejected_by_protected_helper(client: TestClient):
    """Verify require_authenticated_user rejects unauthenticated requests with HTTP 401."""
    # Ensure no cookies set
    client.cookies.clear()
    response = client.get("/test-protected-route")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Authentication required"


def test_role_based_protection_distinguishes_player_and_admin(client: TestClient, db_session: Session):
    """Verify require_role allows ADMIN and rejects PLAYER with HTTP 403."""
    player = register_user(db_session, username="standardplayer", password="Password1$", role=UserRole.PLAYER)
    admin = register_user(db_session, username="systemadmin", password="Password1$", role=UserRole.ADMIN)

    # 1. As PLAYER accessing admin route
    player_token = create_session_token(player.id)
    client.cookies.set(SESSION_COOKIE_NAME, player_token)
    res_player = client.get("/test-admin-route")
    assert res_player.status_code == status.HTTP_403_FORBIDDEN
    assert res_player.json()["detail"] == "Insufficient permissions"

    # 2. As ADMIN accessing admin route
    admin_token = create_session_token(admin.id)
    client.cookies.set(SESSION_COOKIE_NAME, admin_token)
    res_admin = client.get("/test-admin-route")
    assert res_admin.status_code == status.HTTP_200_OK
    assert res_admin.json()["admin"] == "systemadmin"


def test_already_authenticated_redirected_from_auth_pages(client: TestClient, db_session: Session):
    """Verify logged-in users are redirected to / when visiting /login or /register."""
    user = register_user(db_session, username="activeuser", password="Password1$")
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    # Visiting /login while logged in
    res_login = client.get("/login", follow_redirects=False)
    assert res_login.status_code == status.HTTP_303_SEE_OTHER
    assert res_login.headers["location"] == "/"

    # Visiting /register while logged in
    res_register = client.get("/register", follow_redirects=False)
    assert res_register.status_code == status.HTTP_303_SEE_OTHER
    assert res_register.headers["location"] == "/"
