from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.enums.evaluation import LetterEvaluation
from app.enums.game_status import GameStatus


class LetterResult(BaseModel):
    """Evaluation result for a single letter in a guess."""

    letter: str = Field(..., min_length=1, max_length=1, description="The guessed letter")
    result: LetterEvaluation = Field(..., description="Evaluation state: CORRECT, PRESENT, or ABSENT")


class GuessSubmissionRequest(BaseModel):
    """Payload for submitting a guess."""

    guess: str = Field(..., min_length=5, max_length=5, description="5-letter alphabetic guess")


class GuessResultResponse(BaseModel):
    """Response representing an evaluated guess."""

    model_config = ConfigDict(from_attributes=True)

    attempt_number: int = Field(..., ge=1, le=5, description="Attempt number (1-5)")
    guess: str = Field(..., min_length=5, max_length=5, description="Normalized 5-letter guess")
    evaluations: list[LetterResult] = Field(..., min_length=5, max_length=5)


class StartGameResponse(BaseModel):
    """Response returned when a new game is started."""

    game_id: int
    status: GameStatus
    attempts: int
    max_attempts: int = 5
    started_at: datetime
    message: str = "Game started. Guess the 5-letter word within 5 attempts!"


class GameStateResponse(BaseModel):
    """Complete game state response."""

    game_id: int
    status: GameStatus
    attempts: int
    max_attempts: int = 5
    is_active: bool
    guesses: list[GuessResultResponse] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime | None = None
    target_word: str | None = Field(
        default=None,
        description="Concealed while active; revealed only after game completion.",
    )
    message: str | None = None
