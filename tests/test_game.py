from datetime import datetime, timezone
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums.evaluation import LetterEvaluation
from app.enums.game_status import GameStatus
from app.exceptions import (
    GameFinishedError,
    GameNotFoundError,
    InvalidGuessError,
    UnauthorizedGameAccessError,
)
from app.models.game import Game
from app.models.guess import Guess
from app.models.user import User
from app.models.word import Word
from app.routes.auth import SESSION_COOKIE_NAME
from app.services.auth_service import create_session_token, register_user
from app.services.game_service import (
    evaluate_guess,
    get_game_state,
    start_game,
    submit_guess,
    validate_guess,
)
from app.services.word_seed import INITIAL_WORDS, seed_words


# ============================================================================
# 1. Word Data Tests
# ============================================================================


def test_seed_words_creates_exactly_20_words(db_session: Session):
    """Verify exactly 20 seed words exist after seeding."""
    words = seed_words(db_session)
    assert len(words) == 20
    assert len(INITIAL_WORDS) == 20


def test_seed_words_properties(db_session: Session):
    """Verify all words are 5 letters, uppercase, and unique."""
    words = seed_words(db_session)
    word_texts = [w.word for w in words]

    # Exactly 5 letters and alphabetic
    assert all(len(w) == 5 for w in word_texts)
    assert all(w.isalpha() for w in word_texts)

    # Uppercase
    assert all(w.isupper() for w in word_texts)

    # Unique
    assert len(set(word_texts)) == 20


def test_seed_words_idempotent(db_session: Session):
    """Verify running the seed twice does not duplicate words."""
    seed_words(db_session)
    initial_count = db_session.execute(select(Word)).scalars().all()
    assert len(initial_count) == 20

    # Second run
    seed_words(db_session)
    second_count = db_session.execute(select(Word)).scalars().all()
    assert len(second_count) == 20


# ============================================================================
# 2. Wordle-Style Evaluation Tests (including duplicate-letter accounting)
# ============================================================================


def test_evaluate_guess_all_correct():
    """Verify exact target guess produces all CORRECT results."""
    evals = evaluate_guess(target="CRANE", guess="CRANE")
    assert evals == [LetterEvaluation.CORRECT] * 5


def test_evaluate_guess_all_absent():
    """Verify all letters absent from target return ABSENT."""
    evals = evaluate_guess(target="PLANT", guess="CHIME")
    assert evals == [LetterEvaluation.ABSENT] * 5


def test_evaluate_guess_mixed_single_letters():
    """Verify correct letters in wrong positions return PRESENT."""
    # Target: WATER, Guess: TEARS ->
    # T: in WATER (index 2) -> PRESENT
    # E: in WATER (index 3) -> PRESENT
    # A: in WATER (index 1) -> PRESENT
    # R: in WATER (index 4) -> PRESENT
    # S: not in WATER -> ABSENT
    evals = evaluate_guess(target="WATER", guess="TEARS")
    assert evals == [
        LetterEvaluation.PRESENT,
        LetterEvaluation.PRESENT,
        LetterEvaluation.PRESENT,
        LetterEvaluation.PRESENT,
        LetterEvaluation.ABSENT,
    ]


def test_evaluate_guess_duplicate_in_guess_single_in_target():
    """Case 1: Guess contains duplicate letters, but target contains it only once.

    Target: BRAIN (one 'A' at index 2).
    Guess:  ALARM (two 'A's at indices 0 and 2).
    Index 2 is exact match (CORRECT).
    Index 0 should be ABSENT because the only 'A' is already consumed by the exact match.
    """
    evals = evaluate_guess(target="BRAIN", guess="ALARM")
    assert evals[2] == LetterEvaluation.CORRECT
    assert evals[0] == LetterEvaluation.ABSENT


def test_evaluate_guess_duplicate_in_target_single_in_guess():
    """Case 2: Target contains duplicate letters, but guess contains it fewer times.

    Target: APPLE (two 'P's at indices 1 and 2).
    Guess:  PLANT (one 'P' at index 0).
    'P' is at wrong position (0 vs 1,2), so it should be PRESENT.
    """
    evals = evaluate_guess(target="APPLE", guess="PLANT")
    assert evals[0] == LetterEvaluation.PRESENT


def test_evaluate_guess_duplicate_in_both_different_positions():
    """Case 3: Both target and guess contain duplicate letters in different positions.

    Target: SPEED (two 'E's at indices 2 and 3).
    Guess:  ERASE (two 'E's at indices 0 and 4).
    Neither 'E' is in the exact position.
    Both 'E's should be PRESENT because target has two 'E's available.
    """
    evals = evaluate_guess(target="SPEED", guess="ERASE")
    assert evals[0] == LetterEvaluation.PRESENT  # First 'E' consumes one 'E'
    assert evals[4] == LetterEvaluation.PRESENT  # Second 'E' consumes second 'E'


def test_evaluate_guess_three_duplicates_in_guess_one_in_target():
    """Target: WATER (one 'E' at index 3). Guess: EERIE (three 'E's at 0, 1, 4).

    None are in exact position 3.
    First 'E' at index 0 is PRESENT (consumes the 1 'E').
    Subsequent 'E's at indices 1 and 4 must be ABSENT.
    """
    evals = evaluate_guess(target="WATER", guess="EERIE")
    assert evals[0] == LetterEvaluation.PRESENT
    assert evals[1] == LetterEvaluation.ABSENT
    assert evals[4] == LetterEvaluation.ABSENT


# ============================================================================
# 3. Game Start Tests
# ============================================================================


def test_start_game_initial_state(db_session: Session):
    """Verify newly started game has status IN_PROGRESS, 0 attempts, and valid timestamps."""
    seed_words(db_session)
    user = register_user(db_session, username="gamestartuser", password="Password1$")

    game = start_game(db_session, user.id)
    assert game.id is not None
    assert game.user_id == user.id
    assert game.status == GameStatus.IN_PROGRESS
    assert game.attempts == 0
    assert game.started_at is not None
    assert game.completed_at is None

    # Target word exists in database
    target_word = db_session.get(Word, game.word_id)
    assert target_word is not None
    assert target_word.word in INITIAL_WORDS


def test_api_start_game_authenticated(client: TestClient, db_session: Session):
    """Verify authenticated player can start a game via API endpoint."""
    seed_words(db_session)
    user = register_user(db_session, username="apiplayer", password="Password1$")
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    response = client.post("/game/start")
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert "game_id" in data
    assert data["status"] == GameStatus.IN_PROGRESS.value
    assert data["attempts"] == 0
    assert data["max_attempts"] == 5


def test_api_start_game_unauthenticated_rejected(client: TestClient):
    """Verify unauthenticated user cannot start a game."""
    client.cookies.clear()
    response = client.post("/game/start")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# 4. Guess Validation Tests
# ============================================================================


def test_validate_guess_normalization():
    """Verify valid 5-letter guess is normalized to uppercase."""
    assert validate_guess("crane") == "CRANE"
    assert validate_guess(" APPLE ") == "APPLE"


@pytest.mark.parametrize("invalid_guess", [
    "TOOLONGG",   # > 5 chars
    "FOUR",       # < 5 chars
    "CRA12",      # Contains digits
    "CR-NE",      # Contains punctuation
    "     ",      # Whitespace
    "",           # Empty
])
def test_validate_guess_invalid_inputs_rejected(invalid_guess: str):
    """Verify non-5-letter or non-alphabetic guesses raise InvalidGuessError."""
    with pytest.raises(InvalidGuessError):
        validate_guess(invalid_guess)


def test_invalid_guess_does_not_increment_attempts_or_create_row(db_session: Session):
    """Verify invalid guess attempts leave game and database unchanged."""
    seed_words(db_session)
    user = register_user(db_session, username="invalidguesser", password="Password1$")
    game = start_game(db_session, user.id)

    initial_attempts = game.attempts

    with pytest.raises(InvalidGuessError):
        submit_guess(db_session, game_id=game.id, user_id=user.id, raw_guess="BAD12")

    db_session.refresh(game)
    assert game.attempts == initial_attempts

    # No guess rows created
    guesses = db_session.execute(select(Guess).where(Guess.game_id == game.id)).scalars().all()
    assert len(guesses) == 0


def test_player_cannot_guess_on_another_players_game(db_session: Session):
    """Verify unauthorized player cannot submit a guess to someone else's game."""
    seed_words(db_session)
    player1 = register_user(db_session, username="playerone1", password="Password1$")
    player2 = register_user(db_session, username="playertwo2", password="Password1$")

    game1 = start_game(db_session, player1.id)

    with pytest.raises(UnauthorizedGameAccessError):
        submit_guess(db_session, game_id=game1.id, user_id=player2.id, raw_guess="CRANE")


# ============================================================================
# 5. Game Completion Tests (Win & Loss Conditions)
# ============================================================================


def test_game_win_condition(db_session: Session):
    """Verify correct guess changes status to WON, sets completed_at, and increments attempts."""
    user = register_user(db_session, username="winneruser", password="Password1$")
    word = Word(word="CHAIR")
    db_session.add(word)
    db_session.commit()

    game = Game(user_id=user.id, word_id=word.id, status=GameStatus.IN_PROGRESS, attempts=0)
    db_session.add(game)
    db_session.commit()

    guess_obj, evals, updated_game = submit_guess(db_session, game.id, user.id, "CHAIR")

    assert guess_obj.guess == "CHAIR"
    assert guess_obj.attempt_number == 1
    assert all(e == LetterEvaluation.CORRECT for e in evals)

    assert updated_game.status == GameStatus.WON
    assert updated_game.attempts == 1
    assert updated_game.completed_at is not None


def test_game_loss_condition_on_fifth_attempt(db_session: Session):
    """Verify fifth incorrect guess marks game as LOST and sets completed_at."""
    user = register_user(db_session, username="loseruser", password="Password1$")
    word = Word(word="WATER")
    db_session.add(word)
    db_session.commit()

    game = Game(user_id=user.id, word_id=word.id, status=GameStatus.IN_PROGRESS, attempts=0)
    db_session.add(game)
    db_session.commit()

    # 4 incorrect guesses
    for i in range(1, 5):
        guess_obj, _, g = submit_guess(db_session, game.id, user.id, "CLOUD")
        assert g.status == GameStatus.IN_PROGRESS
        assert g.attempts == i

    # 5th incorrect guess
    _, _, final_game = submit_guess(db_session, game.id, user.id, "CLOUD")
    assert final_game.status == GameStatus.LOST
    assert final_game.attempts == 5
    assert final_game.completed_at is not None


def test_cannot_submit_sixth_guess(db_session: Session):
    """Verify sixth guess attempt is rejected with GameFinishedError."""
    user = register_user(db_session, username="sixattemptsuser", password="Password1$")
    word = Word(word="WATER")
    db_session.add(word)
    db_session.commit()

    game = Game(user_id=user.id, word_id=word.id, status=GameStatus.IN_PROGRESS, attempts=0)
    db_session.add(game)
    db_session.commit()

    # Submit 5 guesses to reach LOST
    for _ in range(5):
        submit_guess(db_session, game.id, user.id, "CLOUD")

    # 6th guess must be rejected
    with pytest.raises(GameFinishedError):
        submit_guess(db_session, game.id, user.id, "CLOUD")


def test_cannot_submit_guess_after_won(db_session: Session):
    """Verify guesses cannot be submitted after winning."""
    user = register_user(db_session, username="postwinuser", password="Password1$")
    word = Word(word="BEACH")
    db_session.add(word)
    db_session.commit()

    game = Game(user_id=user.id, word_id=word.id, status=GameStatus.IN_PROGRESS, attempts=0)
    db_session.add(game)
    db_session.commit()

    # Win on first attempt
    submit_guess(db_session, game.id, user.id, "BEACH")
    assert game.status == GameStatus.WON

    # Further guesses rejected
    with pytest.raises(GameFinishedError):
        submit_guess(db_session, game.id, user.id, "CLOUD")


# ============================================================================
# 6. Game State & Information Concealment Tests
# ============================================================================


def test_game_state_target_word_concealed_while_active(db_session: Session):
    """Verify target word is NOT exposed in game state while IN_PROGRESS."""
    user = register_user(db_session, username="secretuser", password="Password1$")
    word = Word(word="SECRET")
    word.word = "EARTH"
    db_session.add(word)
    db_session.commit()

    game = Game(user_id=user.id, word_id=word.id, status=GameStatus.IN_PROGRESS, attempts=0)
    db_session.add(game)
    db_session.commit()

    state = get_game_state(db_session, game.id, user.id)
    assert state["status"] == GameStatus.IN_PROGRESS
    assert state["is_active"] is True
    assert state["target_word"] is None


def test_game_state_target_word_revealed_on_completion(db_session: Session):
    """Verify target word IS exposed in game state once completed (WON or LOST)."""
    user = register_user(db_session, username="revealeduser", password="Password1$")
    word = Word(word="FLAME")
    db_session.add(word)
    db_session.commit()

    game = Game(user_id=user.id, word_id=word.id, status=GameStatus.IN_PROGRESS, attempts=0)
    db_session.add(game)
    db_session.commit()

    # Win game
    submit_guess(db_session, game.id, user.id, "FLAME")

    state = get_game_state(db_session, game.id, user.id)
    assert state["status"] == GameStatus.WON
    assert state["is_active"] is False
    assert state["target_word"] == "FLAME"
    assert "Congratulations" in state["message"]


def test_game_state_previous_guesses_in_order_with_evaluations(db_session: Session):
    """Verify previous guesses are returned in chronological order with evaluations."""
    user = register_user(db_session, username="historyuser", password="Password1$")
    word = Word(word="DANCE")
    db_session.add(word)
    db_session.commit()

    game = Game(user_id=user.id, word_id=word.id, status=GameStatus.IN_PROGRESS, attempts=0)
    db_session.add(game)
    db_session.commit()

    submit_guess(db_session, game.id, user.id, "PLANT")
    submit_guess(db_session, game.id, user.id, "CHAIR")

    state = get_game_state(db_session, game.id, user.id)
    assert len(state["guesses"]) == 2
    assert state["guesses"][0]["attempt_number"] == 1
    assert state["guesses"][0]["guess"] == "PLANT"
    assert state["guesses"][1]["attempt_number"] == 2
    assert state["guesses"][1]["guess"] == "CHAIR"

    # Per-letter evaluations exist
    assert len(state["guesses"][0]["evaluations"]) == 5
    assert "result" in state["guesses"][0]["evaluations"][0]


# ============================================================================
# 7. End-to-End API Game Routes
# ============================================================================


def test_api_guess_submission_flow(client: TestClient, db_session: Session):
    """Verify submitting guesses via API route updates game and returns valid schema."""
    seed_words(db_session)
    user = register_user(db_session, username="apiplayuser", password="Password1$")
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    # Start game
    start_res = client.post("/game/start")
    assert start_res.status_code == status.HTTP_201_CREATED
    game_id = start_res.json()["game_id"]

    # Submit valid guess
    guess_res = client.post(
        f"/game/{game_id}/guess",
        json={"guess": "cloud"},  # lowercase should be normalized
    )
    assert guess_res.status_code == status.HTTP_200_OK
    data = guess_res.json()
    assert data["attempts"] == 1
    assert len(data["guesses"]) == 1
    assert data["guesses"][0]["guess"] == "CLOUD"

    # Fetch game state
    state_res = client.get(f"/game/{game_id}")
    assert state_res.status_code == status.HTTP_200_OK
    state_data = state_res.json()
    assert state_data["game_id"] == game_id
    assert state_data["attempts"] == 1
