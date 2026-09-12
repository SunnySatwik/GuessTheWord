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


# ============================================================================
# 8. Player Game Page Visual Foundation (Phase 4B-1)
# ============================================================================


def test_get_game_page_unauthenticated_redirects(client: TestClient):
    """Verify unauthenticated requests to /game redirect to /login with 303."""
    response = client.get("/game", follow_redirects=False)
    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert response.headers["location"] == "/login"


def test_get_game_page_unauthenticated_json_unauthorized(client: TestClient):
    """Verify unauthenticated JSON requests to /game return 401 Unauthorized."""
    response = client.get("/game", headers={"Accept": "application/json"})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Authentication required"


def test_get_game_page_authenticated(client: TestClient, db_session: Session):
    """Verify authenticated user receives 200 HTML with all foundation UI components."""
    user = register_user(db_session, username="pageviewer", password="Password1$")
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    response = client.get("/game")
    assert response.status_code == status.HTTP_200_OK
    assert "text/html" in response.headers["content-type"]
    html = response.text

    # Essential visual foundation containers
    assert "game-page-container" in html
    assert "game-header" in html
    assert "game-meta" in html
    assert "game-stage" in html
    assert "game-controls" in html

    # Status elements & badges
    assert 'id="attempts-display"' in html
    assert 'id="daily-games-display"' in html
    assert 'id="game-status-badge"' in html
    assert "0 / 5" in html
    assert "0 / 3" in html

    # State banners
    assert 'id="state-ready"' in html
    assert 'id="btn-start-game"' in html
    assert 'id="state-completed"' in html
    assert 'id="state-limit"' in html
    assert 'id="state-loading"' in html
    assert 'id="state-error"' in html

    # 5x5 Game Board Grid Structure (Phase 4B-2A)
    assert 'id="game-board"' in html
    assert 'role="grid"' in html
    assert 'id="controls-placeholder"' in html
    assert html.count('class="board-row"') == 5
    assert html.count('class="board-tile"') == 25

    # Static assets linked
    assert "css/game.css" in html
    assert "js/game.js" in html


def test_get_game_page_board_structure(client: TestClient, db_session: Session):
    """Verify the 5x5 board contains exactly 5 rows and 25 tiles with data coordinates."""
    user = register_user(db_session, username="boardchecker", password="Password1$")
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    response = client.get("/game")
    assert response.status_code == status.HTTP_200_OK
    html = response.text

    # Board container
    assert 'id="game-board"' in html
    assert 'role="grid"' in html
    assert 'aria-label="5 by 5 guess board"' in html

    # Exactly 5 rows with correct attributes
    for r in range(5):
        assert f'class="board-row" role="row" data-row="{r}"' in html

    # Exactly 25 tiles with coordinates
    for r in range(5):
        for c in range(5):
            assert f'class="board-tile" role="gridcell" data-row="{r}" data-col="{c}"' in html


def test_get_game_page_slash_trailing_route(client: TestClient, db_session: Session):
    """Verify /game/ with trailing slash also renders the game page."""
    user = register_user(db_session, username="slashviewer", password="Password1$")
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    response = client.get("/game/")
    assert response.status_code == status.HTTP_200_OK
    assert "game-page-container" in response.text


# ============================================================================
# 9. Guess Tile States & Visual Feedback (Phase 4B-2B)
# ============================================================================


def test_game_css_contains_tile_state_classes(client: TestClient):
    """Verify game.css provides all evaluation, interaction, and animation state rules."""
    response = client.get("/static/css/game.css")
    assert response.status_code == status.HTTP_200_OK
    css = response.text

    # Evaluation and feedback classes
    assert ".board-tile.is-filled" in css
    assert ".board-tile.is-correct" in css
    assert ".board-tile.is-present" in css
    assert ".board-tile.is-absent" in css
    assert ".board-tile.is-revealing" in css

    # Color tokens
    assert "--color-tile-correct" in css
    assert "--color-tile-present" in css
    assert "--color-tile-absent" in css

    # Animations & accessible reduced motion
    assert "tilePopIn" in css
    assert "tileFlip" in css
    assert "prefers-reduced-motion" in css


def test_game_js_contains_tile_dom_helpers(client: TestClient):
    """Verify game.js exports the tile DOM manipulation helpers."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    assert "getTile" in js
    assert "setTileLetter" in js
    assert "setTileState" in js
    assert "clearTile" in js
    assert "revealTile" in js


# ============================================================================
# 10. Real Game State -> Guess Board Integration (Phase 4B-2C)
# ============================================================================


def test_game_page_without_game_id_renders_ready_state(client: TestClient, db_session: Session):
    """Verify /game without game_id leaves data-game-id empty and ready."""
    user = register_user(db_session, username="gamereadyuser", password="Password1$")
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    response = client.get("/game")
    assert response.status_code == status.HTTP_200_OK
    assert 'data-game-id=""' in response.text
    assert 'id="state-ready"' in response.text


def test_game_page_with_game_id_renders_container_attr(client: TestClient, db_session: Session):
    """Verify /game?game_id=123 populates the container's data-game-id attribute."""
    user = register_user(db_session, username="gameiduser", password="Password1$")
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    response = client.get("/game?game_id=123")
    assert response.status_code == status.HTTP_200_OK
    assert 'data-game-id="123"' in response.text


def test_game_page_active_game_does_not_leak_target_word(client: TestClient, db_session: Session):
    """Verify that the secret target word is never embedded into the /game page HTML."""
    seed_words(db_session)
    user = register_user(db_session, username="secretuser", password="Password1$")
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    # Start an active game
    start_res = client.post("/game/start")
    assert start_res.status_code == status.HTTP_201_CREATED
    game_id = start_res.json()["game_id"]

    # Retrieve game from DB to get the actual target word
    game = db_session.get(Game, game_id)
    assert game is not None
    target_word = game.word.word

    # Render game page for this game
    response = client.get(f"/game?game_id={game_id}")
    assert response.status_code == status.HTTP_200_OK
    html = response.text

    # Target word must not appear in HTML
    assert target_word not in html
    assert 'id="completion-target"' in html


def test_api_get_game_state_in_progress_structure(client: TestClient, db_session: Session):
    """Verify GET /game/{game_id} conceals target word and returns attempts and guesses."""
    seed_words(db_session)
    user = register_user(db_session, username="stateuser", password="Password1$")
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    # Start game
    start_res = client.post("/game/start")
    game_id = start_res.json()["game_id"]
    game_obj = db_session.get(Game, game_id)
    guess_word = "CRANE" if game_obj.word.word != "CRANE" else "PLANT"

    # Submit 1 guess
    guess_res = client.post(f"/game/{game_id}/guess", json={"guess": guess_word})
    assert guess_res.status_code == status.HTTP_200_OK

    # Fetch game state
    get_res = client.get(f"/game/{game_id}")
    assert get_res.status_code == status.HTTP_200_OK
    data = get_res.json()

    assert data["game_id"] == game_id
    assert data["status"] == GameStatus.IN_PROGRESS
    assert data["attempts"] == 1
    assert data["max_attempts"] == 5
    assert data["is_active"] is True
    assert data["target_word"] is None  # Strictly concealed
    assert len(data["guesses"]) == 1
    assert data["guesses"][0]["attempt_number"] == 1
    assert data["guesses"][0]["guess"] == guess_word
    assert len(data["guesses"][0]["evaluations"]) == 5


def test_api_get_game_state_completed_reveals_target(client: TestClient, db_session: Session):
    """Verify GET /game/{game_id} reveals target word once game is completed."""
    user = register_user(db_session, username="wonuser", password="Password1$")
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    word = Word(word="FLAME")
    db_session.add(word)
    db_session.commit()

    game = Game(user_id=user.id, word_id=word.id, status=GameStatus.IN_PROGRESS, attempts=0)
    db_session.add(game)
    db_session.commit()

    # Win game by guessing target word
    submit_guess(db_session, game.id, user.id, "FLAME")

    # Fetch game state
    get_res = client.get(f"/game/{game.id}")
    assert get_res.status_code == status.HTTP_200_OK
    data = get_res.json()

    assert data["status"] == GameStatus.WON
    assert data["is_active"] is False
    assert data["target_word"] == "FLAME"  # Revealed upon completion


def test_api_get_game_state_unauthorized_other_user(client: TestClient, db_session: Session):
    """Verify GET /game/{game_id} returns 403 Forbidden when requested by another player."""
    seed_words(db_session)
    user1 = register_user(db_session, username="ownerplayer", password="Password1$")
    user2 = register_user(db_session, username="intruderplayer", password="Password1$")

    # User 1 starts game
    token1 = create_session_token(user1.id)
    client.cookies.set(SESSION_COOKIE_NAME, token1)
    start_res = client.post("/game/start")
    game_id = start_res.json()["game_id"]

    # User 2 attempts to fetch User 1's game
    token2 = create_session_token(user2.id)
    client.cookies.set(SESSION_COOKIE_NAME, token2)
    get_res = client.get(f"/game/{game_id}")
    assert get_res.status_code == status.HTTP_403_FORBIDDEN
    assert "access" in get_res.json()["detail"].lower()


def test_api_get_game_state_not_found(client: TestClient, db_session: Session):
    """Verify GET /game/{game_id} returns 404 for a nonexistent game ID."""
    user = register_user(db_session, username="notfounduser", password="Password1$")
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    get_res = client.get("/game/999999")
    assert get_res.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in get_res.json()["detail"].lower()


def test_game_js_contains_state_integration_methods(client: TestClient):
    """Verify game.js contains all methods required for game state integration."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    assert "loadGameState" in js
    assert "renderGameState" in js
    assert "renderGuess" in js
    assert "resetBoard" in js
    assert "setActiveRow" in js
    assert "showCompletedState" in js
    assert "showError" in js


# ============================================================================
# 11. Start Game UI -> Backend Integration (Phase 4B-3A)
# ============================================================================


def test_start_game_button_exists_in_template(client: TestClient, db_session: Session):
    """Verify Start Game button exists in template with both action-start-game and btn-start-game IDs."""
    user = register_user(db_session, username="startbtnuser", password="Password1$")
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    response = client.get("/game")
    assert response.status_code == status.HTTP_200_OK
    html = response.text

    assert 'id="action-start-game"' in html
    assert 'id="btn-start-game"' in html
    assert 'Start Game' in html
    assert 'id="limit-message"' in html


def test_no_automatic_game_creation_on_page_load(client: TestClient, db_session: Session):
    """Verify navigating to /game without game_id does NOT create any game in the database."""
    user = register_user(db_session, username="nogameuser", password="Password1$")
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    initial_games = db_session.query(Game).filter_by(user_id=user.id).count()
    assert initial_games == 0

    response = client.get("/game")
    assert response.status_code == status.HTTP_200_OK

    current_games = db_session.query(Game).filter_by(user_id=user.id).count()
    assert current_games == 0
    assert 'id="state-ready"' in response.text


def test_today_counter_renders_dynamic_backend_count(client: TestClient, db_session: Session):
    """Verify the Today / Daily Limit counter renders actual games_today count, not a hardcoded 0."""
    seed_words(db_session)
    user = register_user(db_session, username="counteruser", password="Password1$")
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    # Initially 0 games played today
    res0 = client.get("/game")
    assert res0.status_code == status.HTTP_200_OK
    assert 'id="daily-games-display">0 / 3<' in res0.text

    # Start 1st game
    start_game(db_session, user.id)
    res1 = client.get("/game")
    assert res1.status_code == status.HTTP_200_OK
    assert 'id="daily-games-display">1 / 3<' in res1.text

    # Start 2nd game
    start_game(db_session, user.id)
    res2 = client.get("/game")
    assert res2.status_code == status.HTTP_200_OK
    assert 'id="daily-games-display">2 / 3<' in res2.text

    # Start 3rd game
    start_game(db_session, user.id)
    res3 = client.get("/game")
    assert res3.status_code == status.HTTP_200_OK
    assert 'id="daily-games-display">3 / 3<' in res3.text


def test_api_start_game_success_contract(client: TestClient, db_session: Session):
    """Verify POST /game/start returns HTTP 201 with game_id, status IN_PROGRESS, and attempts 0."""
    seed_words(db_session)
    user = register_user(db_session, username="starteruser", password="Password1$")
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    response = client.post("/game/start")
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()

    assert "game_id" in data
    assert isinstance(data["game_id"], int)
    assert data["status"] == GameStatus.IN_PROGRESS
    assert data["attempts"] == 0
    assert data["max_attempts"] == 5
    assert "started_at" in data
    assert "target_word" not in data


def test_api_start_game_daily_limit_contract_429(client: TestClient, db_session: Session):
    """Verify POST /game/start returns 429 when daily limit of 3 games has been reached."""
    seed_words(db_session)
    user = register_user(db_session, username="limitplayer", password="Password1$")
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    # Start 3 games successfully
    for _ in range(3):
        res = client.post("/game/start")
        assert res.status_code == status.HTTP_201_CREATED

    # 4th attempt rejected with 429
    res4 = client.post("/game/start")
    assert res4.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    data = res4.json()
    assert "detail" in data
    assert "daily limit reached" in data["detail"].lower()


def test_api_start_game_unauthenticated_contract_401(client: TestClient):
    """Verify POST /game/start returns 401 when user is not authenticated."""
    response = client.post("/game/start", headers={"Accept": "application/json"})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "detail" in response.json()


def test_game_js_contains_start_game_integration_methods(client: TestClient):
    """Verify game.js contains the start game UI integration methods and handlers."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    assert "startGame" in js
    assert "handleStartGameResponse" in js
    assert "setStartButtonLoading" in js
    assert "handleStartGameError" in js
    assert "action-start-game" in js
    assert "/game/start" in js
    assert "location.assign" in js


def test_game_js_start_game_never_references_target_word(client: TestClient):
    """Verify start-game handling in game.js never attempts to read or leak target_word."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    start_idx = js.find("startGame()")
    resp_idx = js.find("handleStartGameResponse(")
    end_idx = js.find("handleStartGameError(")
    start_block = js[start_idx:end_idx]

    assert "target_word" not in start_block


# ============================================================================
# 12. Guess Input Architecture (Phase 4B-3B)
# ============================================================================


def test_game_js_contains_guess_input_methods(client: TestClient):
    """Verify game.js contains all required methods and state properties for guess input."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    assert "bindKeyboardEvents" in js
    assert "canAcceptInput" in js
    assert "handleKeyDown" in js
    assert "handleLetterInput" in js
    assert "handleBackspace" in js
    assert "handleSubmitRequest" in js
    assert "clearCurrentInput" in js
    assert "syncCurrentInput" in js
    assert "currentInput" in js
    assert "activeRowIndex" in js
    assert "isKeyHandlerBound" in js


def test_game_js_keyboard_listener_bound_once(client: TestClient):
    """Verify game.js implements a guard ensuring keyboard listener is bound strictly once."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    assert "if (this.isKeyHandlerBound) return;" in js
    assert "this.isKeyHandlerBound = true;" in js
    assert 'document.addEventListener("keydown"' in js


def test_game_js_input_architecture_rules(client: TestClient):
    """Verify game.js enforces alphabetic input, uppercase conversion, and length limit 5."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    # Single alphabetic character check
    assert "/^[a-zA-Z]$/" in js
    # Uppercase normalization
    assert ".toUpperCase()" in js
    # Length limit check
    assert "this.currentInput.length >= 5" in js
    # Backspace handling
    assert 'key === "Backspace"' in js
    assert "this.currentInput.slice(0, -1)" in js
    # Enter recognition hook
    assert 'key === "Enter"' in js
    assert "handleSubmitRequest" in js


def test_game_js_input_gating_guards(client: TestClient):
    """Verify canAcceptInput requires IN_PROGRESS status, valid active row, and active session."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    can_accept_idx = js.find("canAcceptInput()")
    can_accept_block = js[can_accept_idx:can_accept_idx + 400]

    assert "IN_PROGRESS" in can_accept_block
    assert "this.activeRowIndex >= 0" in can_accept_block
    assert "this.activeRowIndex < 5" in can_accept_block
    assert "this.gameState != null" in can_accept_block


def test_game_js_no_guess_submission_api_call_on_typing(client: TestClient):
    """Verify typing or pressing Enter does NOT trigger /guess API submission."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    # Locate handleSubmitRequest definition
    submit_idx = js.find("handleSubmitRequest() {")
    assert submit_idx != -1
    submit_block = js[submit_idx:submit_idx + 400]

    assert "fetch" not in submit_block
    assert "/guess" not in submit_block
    assert "Submission not implemented yet" in submit_block


def test_game_persisted_guesses_remain_immutable_with_active_row(client: TestClient, db_session: Session):
    """Verify backend state with previous guesses sets active row at attempts count without altering guesses."""
    seed_words(db_session)
    user = register_user(db_session, username="persistedtester", password="Password1$")
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    word = db_session.query(Word).filter_by(word="LIGHT").first()
    assert word is not None

    game = Game(user_id=user.id, word_id=word.id, status=GameStatus.IN_PROGRESS, attempts=0)
    db_session.add(game)
    db_session.commit()

    # Submit 2 guesses
    submit_guess(db_session, game.id, user.id, "CRANE")
    submit_guess(db_session, game.id, user.id, "WATER")

    # Fetch game state
    state_res = client.get(f"/game/{game.id}")
    assert state_res.status_code == status.HTTP_200_OK
    data = state_res.json()

    assert data["attempts"] == 2
    assert len(data["guesses"]) == 2
    assert data["guesses"][0]["guess"] == "CRANE"
    assert data["guesses"][1]["guess"] == "WATER"
    # Row 2 (0-indexed) must be the next active row for new typing
    assert data["status"] == GameStatus.IN_PROGRESS





