from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import BASE_DIR, settings
from app.database import get_db
from app.enums.role import UserRole
from app.models.user import User
from app.schemas.auth import validate_password, validate_username
from app.services.auth_service import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE,
    authenticate_user,
    create_session_token,
    decode_session_token,
    get_user_by_id,
    register_user,
)

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


# ============================================================================
# Session & Dependency Helpers
# ============================================================================


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User | None:
    """Retrieve the authenticated user from the signed session cookie, or None."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None

    user_id = decode_session_token(token)
    if not user_id:
        return None

    return get_user_by_id(db, user_id)


def require_authenticated_user(
    user: User | None = Depends(get_current_user),
) -> User:
    """Require an authenticated user; raises HTTP 401 if unauthenticated."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


def require_role(*roles: UserRole):
    """Dependency factory ensuring authenticated user possesses one of the required roles."""

    def role_checker(user: User = Depends(require_authenticated_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return role_checker


async def _extract_credentials(request: Request) -> tuple[str, str]:
    """Helper to extract username and password from form data or JSON body."""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
            return str(body.get("username", "")).strip(), str(body.get("password", ""))
        except Exception:
            return "", ""
    form = await request.form()
    return str(form.get("username", "")).strip(), str(form.get("password", ""))


def _is_json_request(request: Request) -> bool:
    """Check if request accepts or expects JSON."""
    content_type = request.headers.get("content-type", "")
    accept = request.headers.get("accept", "")
    return "application/json" in content_type or (
        "application/json" in accept and "text/html" not in accept
    )


# ============================================================================
# Registration Endpoints
# ============================================================================


@router.get("/register", response_class=HTMLResponse)
def register_page(
    request: Request,
    user: User | None = Depends(get_current_user),
) -> Response:
    """Render the registration page. Redirects to / if already logged in."""
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="auth/register.html",
        context={"user": None, "error": None},
    )


@router.post("/register")
async def register_submit(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
) -> Response:
    """Process user registration with server-side validation."""
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    username, password = await _extract_credentials(request)
    is_json = _is_json_request(request)

    # 1. Validate username
    valid_u, u_error = validate_username(username)
    if not valid_u:
        if is_json:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": u_error},
            )
        return templates.TemplateResponse(
            request=request,
            name="auth/register.html",
            context={"username": username, "error": u_error, "user": None},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 2. Validate password
    valid_p, p_error = validate_password(password)
    if not valid_p:
        if is_json:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": p_error},
            )
        return templates.TemplateResponse(
            request=request,
            name="auth/register.html",
            context={"username": username, "error": p_error, "user": None},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 3. Create user in database
    try:
        new_user = register_user(db, username=username, password=password)
    except ValueError as e:
        err_msg = str(e)
        if is_json:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": err_msg},
            )
        return templates.TemplateResponse(
            request=request,
            name="auth/register.html",
            context={"username": username, "error": err_msg, "user": None},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if is_json:
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "message": "User registered successfully",
                "username": new_user.username,
            },
        )

    return RedirectResponse(
        url="/login?registered=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ============================================================================
# Login Endpoints
# ============================================================================


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    user: User | None = Depends(get_current_user),
    registered: str | None = None,
) -> Response:
    """Render the login page. Redirects to / if already logged in."""
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    success_msg = (
        "Registration successful! Please log in with your new credentials."
        if registered == "1"
        else None
    )

    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={"user": None, "error": None, "success": success_msg},
    )


@router.post("/login")
async def login_submit(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
) -> Response:
    """Process user login, verifying credentials and issuing a signed session cookie."""
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    username, password = await _extract_credentials(request)
    is_json = _is_json_request(request)

    authenticated_user = authenticate_user(db, username=username, password=password)
    if not authenticated_user:
        error_msg = "Invalid username or password."
        if is_json:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": error_msg},
            )
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={"username": username, "error": error_msg, "user": None},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Issue secure signed session cookie
    token = create_session_token(authenticated_user.id)

    if is_json:
        response = JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "Login successful",
                "username": authenticated_user.username,
                "role": authenticated_user.role.value,
            },
        )
    else:
        response = RedirectResponse(
            url="/",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE,
        path="/",
        httponly=True,
        samesite="lax",
        secure=(settings.app_env == "production"),
    )
    return response


# ============================================================================
# Logout Endpoints
# ============================================================================


@router.post("/logout")
@router.get("/logout")
def logout(request: Request) -> Response:
    """Clear session cookie and redirect to /login."""
    is_json = _is_json_request(request)
    if is_json:
        response = JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "Logged out successfully"},
        )
    else:
        response = RedirectResponse(
            url="/login",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
    )
    return response
