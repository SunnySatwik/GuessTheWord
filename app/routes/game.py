from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.exceptions import (
    DailyLimitReachedError,
    GameFinishedError,
    GameNotFoundError,
    InvalidGuessError,
    UnauthorizedGameAccessError,
)
from app.models.user import User
from app.routes.auth import require_authenticated_user
from app.schemas.game import (
    GameStateResponse,
    StartGameResponse,
)
from app.services.game_service import (
    get_game_state,
    start_game,
    submit_guess,
)

router = APIRouter(prefix="/game", tags=["game"])


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
