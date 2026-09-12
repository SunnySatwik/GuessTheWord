from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.database import get_db
from app.exceptions import (
    DailyLimitReachedError,
    GameFinishedError,
    GameNotFoundError,
    InvalidGuessError,
    UnauthorizedGameAccessError,
)
from app.models.user import User
from app.routes.auth import _is_json_request, get_current_user, require_authenticated_user
from app.schemas.game import (
    GameStateResponse,
    StartGameResponse,
)
from app.services.game_service import (
    MAX_DAILY_GAMES,
    count_daily_games,
    get_game_state,
    start_game,
    submit_guess,
)

router = APIRouter(prefix="/game", tags=["game"])
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def game_page(
    request: Request,
    game_id: str | None = None,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Render the player game page visual foundation. Requires authentication."""
    if not user:
        if _is_json_request(request):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authentication required"},
            )
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    games_today = count_daily_games(db, user.id)
    return templates.TemplateResponse(
        request=request,
        name="game/game.html",
        context={
            "user": user,
            "games_today": games_today,
            "max_daily_games": MAX_DAILY_GAMES,
            "game_id": game_id or "",
        },
    )


async def _extract_guess_text(request: Request) -> str:
    """Extract guess string from JSON body or Form data."""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
            return str(body.get("guess", "")).strip()
        except Exception:
            return ""
    form = await request.form()
    return str(form.get("guess", "")).strip()


@router.post("/start", response_model=StartGameResponse, status_code=status.HTTP_201_CREATED)
def start_new_game(
    db: Session = Depends(get_db),
    user: User = Depends(require_authenticated_user),
) -> Any:
    """Start a new game session. Enforces max 3 games per calendar day."""
    try:
        game = start_game(db, user_id=user.id)
        return StartGameResponse(
            game_id=game.id,
            status=game.status,
            attempts=game.attempts,
            max_attempts=5,
            started_at=game.started_at,
            message="Game started. Guess the 5-letter word within 5 attempts!",
        )
    except DailyLimitReachedError as e:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": e.message},
        )


@router.post("/{game_id}/guess", response_model=GameStateResponse)
async def make_guess(
    game_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_authenticated_user),
) -> Any:
    """Submit a guess for an ongoing game session."""
    raw_guess = await _extract_guess_text(request)

    try:
        submit_guess(db, game_id=game_id, user_id=user.id, raw_guess=raw_guess)
        state = get_game_state(db, game_id=game_id, user_id=user.id)
        return GameStateResponse(**state)
    except InvalidGuessError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": e.message},
        )
    except GameNotFoundError as e:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": e.message},
        )
    except UnauthorizedGameAccessError as e:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": e.message},
        )
    except GameFinishedError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": e.message},
        )


@router.get("/{game_id}", response_model=GameStateResponse)
def get_game(
    game_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_authenticated_user),
) -> Any:
    """Retrieve full game state including previous guesses and evaluation results."""
    try:
        state = get_game_state(db, game_id=game_id, user_id=user.id)
        return GameStateResponse(**state)
    except GameNotFoundError as e:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": e.message},
        )
    except UnauthorizedGameAccessError as e:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": e.message},
        )
