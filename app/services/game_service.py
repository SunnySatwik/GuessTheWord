import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums.evaluation import LetterEvaluation
from app.enums.game_status import GameStatus
from app.exceptions import (
    DailyLimitReachedError,
    GameFinishedError,
    GameNotFoundError,
    InvalidGuessError,
    UnauthorizedGameAccessError,
)
from app.models.game import Game
from app.models.guess import Guess
from app.models.word import Word
from app.services.word_seed import seed_words

# Game rules constants
MAX_ATTEMPTS: int = 5
MAX_DAILY_GAMES: int = 3
WORD_LENGTH: int = 5


# ============================================================================
# Guess Evaluation Algorithm (Wordle-Style with Duplicate Letter Accounting)
# ============================================================================


def evaluate_guess(target: str, guess: str) -> list[LetterEvaluation]:
    """Evaluate a 5-letter guess against the target word using standard Wordle rules.

    Two-pass accounting ensures letters are not counted more times than they exist:
    1. Pass 1: Mark exact position matches (CORRECT) and decrement available counts.
    2. Pass 2: Mark remaining letters found in target as PRESENT, and others as ABSENT.
    """
    target = target.strip().upper()
    guess = guess.strip().upper()

    if len(target) != WORD_LENGTH or len(guess) != WORD_LENGTH:
        raise ValueError(f"Target and guess must both be exactly {WORD_LENGTH} characters.")

    results: list[LetterEvaluation] = [LetterEvaluation.ABSENT] * WORD_LENGTH

    # Count letters in target that are NOT matched in pass 1
    target_counts: Counter[str] = Counter()
    for i in range(WORD_LENGTH):
        if guess[i] == target[i]:
            results[i] = LetterEvaluation.CORRECT
        else:
            target_counts[target[i]] += 1

    # Pass 2: Check remaining letters for PRESENT or ABSENT
    for i in range(WORD_LENGTH):
        if results[i] == LetterEvaluation.CORRECT:
            continue
        g_char = guess[i]
        if target_counts[g_char] > 0:
            results[i] = LetterEvaluation.PRESENT
            target_counts[g_char] -= 1
        else:
            results[i] = LetterEvaluation.ABSENT

    return results


# ============================================================================
# Daily Limit Counting
# ============================================================================


def count_daily_games(db: Session, user_id: int, reference_dt: datetime | None = None) -> int:
    """Count game sessions started by a user on the calendar day of reference_dt (UTC)."""
    ref = reference_dt or datetime.now(timezone.utc)
    day_start = ref.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    count = db.execute(
        select(func.count(Game.id)).where(
            Game.user_id == user_id,
            Game.started_at >= day_start,
            Game.started_at < day_end,
        )
    ).scalar_one()

    return count


# ============================================================================
# Game Life-Cycle Service Functions
# ============================================================================


def start_game(db: Session, user_id: int) -> Game:
    """Start a new game session for an authenticated user.

    Enforces the daily limit of 3 games per calendar day.
    Selects a random target word from the words table.
    """
    # Check daily limit
    games_today = count_daily_games(db, user_id)
    if games_today >= MAX_DAILY_GAMES:
        raise DailyLimitReachedError(
            f"Daily limit reached. You can only play {MAX_DAILY_GAMES} games per calendar day."
        )

    # Fetch available words
    words = db.execute(select(Word)).scalars().all()
    if not words:
        words = seed_words(db)

    selected_word = random.choice(words)

    game = Game(
        user_id=user_id,
        word_id=selected_word.id,
        status=GameStatus.IN_PROGRESS,
        attempts=0,
        started_at=datetime.now(timezone.utc),
        completed_at=None,
    )
    db.add(game)
    db.commit()
    db.refresh(game)
    return game


def validate_guess(raw_guess: str) -> str:
    """Validate and normalize a user guess.

    Must be exactly 5 alphabetic characters.
    Returns the normalized uppercase string.
    """
    cleaned = raw_guess.strip() if raw_guess else ""
    if len(cleaned) != WORD_LENGTH or not cleaned.isalpha():
        raise InvalidGuessError(f"Guess must be exactly {WORD_LENGTH} alphabetic letters.")
    return cleaned.upper()


def submit_guess(
    db: Session,
    game_id: int,
    user_id: int,
    raw_guess: str,
) -> tuple[Guess, list[LetterEvaluation], Game]:
    """Process a guess submission for an ongoing game session.

    Validates ownership, active game status, attempts boundary, and guess format.
    Evaluates guess, records the Guess row, updates attempts, and handles WIN/LOSS.
    """
    game = db.get(Game, game_id)
    if not game:
        raise GameNotFoundError("Game not found.")

    if game.user_id != user_id:
        raise UnauthorizedGameAccessError("You do not have access to this game.")

    if game.status != GameStatus.IN_PROGRESS:
        raise GameFinishedError("This game is already finished.")

    if game.attempts >= MAX_ATTEMPTS:
        raise GameFinishedError(f"Maximum number of attempts ({MAX_ATTEMPTS}) has been reached.")

    # Validate guess format
    clean_guess = validate_guess(raw_guess)

    attempt_number = game.attempts + 1
    evaluations = evaluate_guess(game.word.word, clean_guess)

    # Create Guess record
    guess_obj = Guess(
        game_id=game.id,
        guess=clean_guess,
        attempt_number=attempt_number,
        created_at=datetime.now(timezone.utc),
    )
    db.add(guess_obj)
    game.attempts += 1

    # Check Win Condition
    if clean_guess == game.word.word:
        game.status = GameStatus.WON
        game.completed_at = datetime.now(timezone.utc)
    # Check Loss Condition
    elif game.attempts >= MAX_ATTEMPTS:
        game.status = GameStatus.LOST
        game.completed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(guess_obj)
    db.refresh(game)

    return guess_obj, evaluations, game


def get_game_state(db: Session, game_id: int, user_id: int) -> dict[str, Any]:
    """Retrieve full game state including previous guesses and per-letter evaluations.

    Crucially, hides the target word while the game is IN_PROGRESS.
    """
    game = db.get(Game, game_id)
    if not game:
        raise GameNotFoundError("Game not found.")

    if game.user_id != user_id:
        raise UnauthorizedGameAccessError("You do not have access to this game.")

    # Load guesses in attempt order
    guesses = db.execute(
        select(Guess).where(Guess.game_id == game.id).order_by(Guess.attempt_number)
    ).scalars().all()

    previous_guesses = []
    for g in guesses:
        evals = evaluate_guess(game.word.word, g.guess)
        previous_guesses.append({
            "attempt_number": g.attempt_number,
            "guess": g.guess,
            "evaluations": [
                {"letter": g.guess[idx], "result": evals[idx]}
                for idx in range(WORD_LENGTH)
            ],
        })

    is_active = (game.status == GameStatus.IN_PROGRESS)
    target_word = game.word.word if not is_active else None

    # Status message
    message: str | None = None
    if game.status == GameStatus.WON:
        message = "Congratulations! You guessed the word correctly!"
    elif game.status == GameStatus.LOST:
        message = f"Better luck next time! The correct word was {game.word.word}."

    return {
        "game_id": game.id,
        "status": game.status,
        "attempts": game.attempts,
        "max_attempts": MAX_ATTEMPTS,
        "is_active": is_active,
        "guesses": previous_guesses,
        "started_at": game.started_at,
        "completed_at": game.completed_at,
        "target_word": target_word,
        "message": message,
    }
