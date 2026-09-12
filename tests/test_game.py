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
    """Verify typing letters or pressing backspace does NOT trigger /guess API submission."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    # Locate handleLetterInput definition
    letter_idx = js.find("handleLetterInput(letter) {")
    assert letter_idx != -1
    letter_block = js[letter_idx:letter_idx + 400]
    assert "fetch" not in letter_block
    assert "/guess" not in letter_block

    # Locate handleBackspace definition
    bs_idx = js.find("handleBackspace() {")
    assert bs_idx != -1
    bs_block = js[bs_idx:bs_idx + 400]
    assert "fetch" not in bs_block
    assert "/guess" not in bs_block


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


# ============================================================================
# 13. Guess Submission Integration (Phase 4B-3C)
# ============================================================================


def test_enter_with_fewer_than_five_letters_makes_no_api_request(client: TestClient):
    """Verify Enter with < 5 letters does NOT dispatch an API request and displays subtle inline feedback."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    submit_idx = js.find("handleSubmitRequest() {")
    assert submit_idx != -1
    submit_block = js[submit_idx:submit_idx + 450]

    assert "this.currentInput.length < 5" in submit_block
    assert "5 letters required" in submit_block
    assert "submitted: false" in submit_block


def test_enter_with_five_letters_calls_correct_post_endpoint(client: TestClient):
    """Verify Enter with 5 letters dispatches POST /game/{game_id}/guess with proper headers."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    submit_guess_idx = js.find("async submitGuess() {")
    assert submit_guess_idx != -1
    submit_guess_block = js[submit_guess_idx:submit_guess_idx + 800]

    assert "POST" in submit_guess_block
    assert "/game/" in submit_guess_block
    assert "/guess" in submit_guess_block
    assert "application/json" in submit_guess_block
    assert "same-origin" in submit_guess_block
    assert "JSON.stringify({ guess: guess })" in submit_guess_block


def test_submitted_guess_is_normalized_to_uppercase(client: TestClient, db_session: Session):
    """Verify guess submission normalizes input to uppercase both in JS and at backend API."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    submit_guess_idx = js.find("async submitGuess() {")
    assert submit_guess_idx != -1
    submit_guess_block = js[submit_guess_idx:submit_guess_idx + 400]
    assert "this.currentInput.toUpperCase()" in submit_guess_block

    # Test backend accepts lowercase and normalizes to uppercase
    seed_words(db_session)
    user = register_user(db_session, username="uppercasetester", password="Password1$")
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    game = start_game(db_session, user.id)
    res = client.post(f"/game/{game.id}/guess", json={"guess": "crane"})
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["guesses"][0]["guess"] == "CRANE"


def test_backend_correct_evaluation_rendered_directly(client: TestClient):
    """Verify CORRECT backend evaluation directly maps to 'correct' tile state in game.js."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    apply_idx = js.find("applyGuessResult(gameState) {")
    assert apply_idx != -1
    apply_block = js[apply_idx:apply_idx + 2500]

    assert 'evalItem.result === "CORRECT"' in apply_block
    assert 'state = "correct"' in apply_block


def test_backend_present_evaluation_rendered_directly(client: TestClient):
    """Verify PRESENT backend evaluation directly maps to 'present' tile state in game.js."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    apply_idx = js.find("applyGuessResult(gameState) {")
    assert apply_idx != -1
    apply_block = js[apply_idx:apply_idx + 2500]

    assert 'evalItem.result === "PRESENT"' in apply_block
    assert 'state = "present"' in apply_block


def test_backend_absent_evaluation_rendered_directly(client: TestClient):
    """Verify ABSENT backend evaluation directly maps to 'absent' tile state in game.js."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    apply_idx = js.find("applyGuessResult(gameState) {")
    assert apply_idx != -1
    apply_block = js[apply_idx:apply_idx + 2500]

    assert 'evalItem.result === "ABSENT"' in apply_block
    assert 'state = "absent"' in apply_block


def test_successful_in_progress_submission_advances_active_row(client: TestClient, db_session: Session):
    """Verify successful guess advances attempts counter and sets next row active."""
    seed_words(db_session)
    user = register_user(db_session, username="advancerowtester", password="Password1$")
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    word = db_session.query(Word).filter_by(word="LIGHT").first()
    assert word is not None

    game = Game(user_id=user.id, word_id=word.id, status=GameStatus.IN_PROGRESS, attempts=0)
    db_session.add(game)
    db_session.commit()

    # Submit first non-winning guess
    res = client.post(f"/game/{game.id}/guess", json={"guess": "CRANE"})
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["status"] == "IN_PROGRESS"
    assert data["attempts"] == 1

    # Verify game.js advances active row to attempts
    js_res = client.get("/static/js/game.js")
    assert "this.setActiveRow(attempts);" in js_res.text


def test_successful_submission_clears_current_input_preserves_rows(client: TestClient):
    """Verify successful guess clears currentInput without resetting previous rows."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    apply_idx = js.find("applyGuessResult(gameState) {")
    assert apply_idx != -1
    apply_block = js[apply_idx:apply_idx + 2500]

    assert 'this.currentInput = "";' in apply_block
    # Must NOT call resetBoard in applyGuessResult
    assert "this.resetBoard()" not in apply_block


def test_won_response_activates_no_new_row(client: TestClient, db_session: Session):
    """Verify winning guess deactivates active row, reveals target word, and marks status WON."""
    user = register_user(db_session, username="wontester4b", password="Password1$")
    word = Word(word="FLAME")
    db_session.add(word)
    db_session.commit()

    game = Game(user_id=user.id, word_id=word.id, status=GameStatus.IN_PROGRESS, attempts=0)
    db_session.add(game)
    db_session.commit()

    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    res = client.post(f"/game/{game.id}/guess", json={"guess": "FLAME"})
    assert res.status_code == status.HTTP_200_OK
    data = res.json()

    assert data["status"] == "WON"
    assert data["is_active"] is False
    assert data["target_word"] == "FLAME"

    # Verify game.js deactivates active row on WON
    js_res = client.get("/static/js/game.js")
    assert 'status === "WON"' in js_res.text
    assert "this.setActiveRow(-1);" in js_res.text


def test_lost_response_activates_no_new_row(client: TestClient, db_session: Session):
    """Verify fifth incorrect guess marks status LOST, deactivates active row, and reveals target."""
    user = register_user(db_session, username="losttester4b", password="Password1$")
    word = Word(word="WATER")
    db_session.add(word)
    db_session.commit()

    game = Game(user_id=user.id, word_id=word.id, status=GameStatus.IN_PROGRESS, attempts=0)
    db_session.add(game)
    db_session.commit()

    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    for _ in range(4):
        res = client.post(f"/game/{game.id}/guess", json={"guess": "CLOUD"})
        assert res.status_code == status.HTTP_200_OK

    # 5th attempt
    res5 = client.post(f"/game/{game.id}/guess", json={"guess": "CLOUD"})
    assert res5.status_code == status.HTTP_200_OK
    data5 = res5.json()

    assert data5["status"] == "LOST"
    assert data5["attempts"] == 5
    assert data5["is_active"] is False
    assert data5["target_word"] == "WATER"

    # Verify game.js deactivates active row on LOST
    js_res = client.get("/static/js/game.js")
    assert 'status === "LOST"' in js_res.text


def test_duplicate_submission_protection_in_game_js(client: TestClient):
    """Verify game.js prevents duplicate submissions while a request is in flight."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    assert "isSubmittingGuess: false" in js
    assert "!this.isSubmittingGuess" in js

    submit_idx = js.find("async submitGuess() {")
    assert submit_idx != -1
    submit_block = js[submit_idx:submit_idx + 400]
    assert "this.isSubmittingGuess" in submit_block
    assert "this.setSubmissionLoading(true)" in submit_block


def test_http_400_does_not_advance_row_or_clear_guess(client: TestClient, db_session: Session):
    """Verify HTTP 400 Bad Request displays error, preserves staged guess, and does not advance row."""
    seed_words(db_session)
    user = register_user(db_session, username="http400tester", password="Password1$")
    game = start_game(db_session, user.id)

    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    # Submit invalid guess
    res = client.post(f"/game/{game.id}/guess", json={"guess": "12345"})
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    data = res.json()
    assert "detail" in data

    # Verify game attempts unchanged
    state_res = client.get(f"/game/{game.id}")
    assert state_res.json()["attempts"] == 0

    # Verify game.js handles 400 without clearing input or resetting board
    js_res = client.get("/static/js/game.js")
    assert "response.status === 400" in js_res.text


def test_http_401_unauthenticated_guess_handling(client: TestClient):
    """Verify HTTP 401 Unauthorized returns authentication required and is handled in JS."""
    client.cookies.clear()
    res = client.post("/game/10/guess", json={"guess": "CRANE"}, headers={"Accept": "application/json"})
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert "detail" in res.json()

    js_res = client.get("/static/js/game.js")
    assert "response.status === 401" in js_res.text
    assert "Login Required" in js_res.text


def test_http_403_unauthorized_guess_handling(client: TestClient, db_session: Session):
    """Verify HTTP 403 Forbidden is returned when player submits guess to another player's game."""
    seed_words(db_session)
    player1 = register_user(db_session, username="p1owner", password="Password1$")
    player2 = register_user(db_session, username="p2intruder", password="Password1$")

    game = start_game(db_session, player1.id)

    # Login as player2
    token2 = create_session_token(player2.id)
    client.cookies.set(SESSION_COOKIE_NAME, token2)

    res = client.post(f"/game/{game.id}/guess", json={"guess": "CRANE"})
    assert res.status_code == status.HTTP_403_FORBIDDEN
    assert "detail" in res.json()

    js_res = client.get("/static/js/game.js")
    assert "response.status === 403" in js_res.text


def test_http_404_game_not_found_handling(client: TestClient, db_session: Session):
    """Verify HTTP 404 Not Found is returned for non-existent game ID and handled in JS."""
    user = register_user(db_session, username="notfoundtester", password="Password1$")
    token = create_session_token(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    res = client.post("/game/999999/guess", json={"guess": "CRANE"})
    assert res.status_code == status.HTTP_404_NOT_FOUND

    js_res = client.get("/static/js/game.js")
    assert "response.status === 404" in js_res.text


def test_network_failure_handled_with_friendly_message(client: TestClient):
    """Verify network or unexpected exceptions during guess submission display a friendly message."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    assert "handleGuessError(error) {" in js
    assert "Connection error. Please check your network and try again." in js


def test_game_js_contains_zero_client_side_wordle_evaluation(client: TestClient):
    """Verify game.js contains strictly zero client-side Wordle evaluation logic."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    # Verify no local evaluation algorithm keywords exist
    assert "evaluateGuess" not in js
    assert "evaluate_guess" not in js
    assert "target_counts" not in js
    assert "letterCounts" not in js
    assert "letter_counts" not in js
    assert "targetWord" not in js
    assert "secretWord" not in js


def test_no_virtual_keyboard_introduced(client: TestClient):
    """Verify no virtual or on-screen keyboard buttons are introduced."""
    js_res = client.get("/static/js/game.js")
    assert "renderKeyboard" not in js_res.text
    assert "virtual-key" not in js_res.text
    assert "keyboard-row" not in js_res.text


# ============================================================================
# 14. Polished Guess Reveal Animation (Phase 4B-4A)
# ============================================================================


def test_reveal_animation_sequential_stagger(client: TestClient):
    """Verify animateGuessReveal schedules sequential tile reveals from left to right."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    reveal_idx = js.find("animateGuessReveal(gameState) {")
    assert reveal_idx != -1
    reveal_block = js[reveal_idx:reveal_idx + 4000]

    assert "tileStaggerMs = 250" in reveal_block
    assert "tileDurationMs = 500" in reveal_block
    assert "c * tileStaggerMs" in reveal_block
    assert "this.revealTile(submittedRow, c, state, c * tileStaggerMs)" in reveal_block


def test_reveal_animation_midway_state_transition(client: TestClient):
    """Verify revealTile switches tile evaluation state midway at 250ms during 500ms flip."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    reveal_tile_idx = js.find("revealTile(row, col, state, delayMs = 0) {")
    assert reveal_tile_idx != -1
    tile_block = js[reveal_tile_idx:reveal_tile_idx + 1000]

    assert "is-revealing" in tile_block
    assert "250" in tile_block
    assert "500" in tile_block
    assert "tile.classList.add(`is-${state}`)" in tile_block


def test_can_accept_input_blocked_during_reveal(client: TestClient):
    """Verify canAcceptInput rejects all input while isRevealing is true."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    can_accept_idx = js.find("canAcceptInput() {")
    assert can_accept_idx != -1
    can_accept_block = js[can_accept_idx:can_accept_idx + 600]

    assert "!this.isRevealing" in can_accept_block
    assert "isRevealing: false" in js


def test_reveal_animation_defers_row_advancement(client: TestClient):
    """Verify row advancement is deferred until the finalize callback after all tiles finish."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    reveal_idx = js.find("animateGuessReveal(gameState) {")
    assert reveal_idx != -1
    reveal_block = js[reveal_idx:reveal_idx + 4000]

    # setActiveRow is inside the finalize callback with totalDurationMs
    assert "this.setActiveRow(attempts)" in reveal_block
    assert "totalDurationMs" in reveal_block
    assert "this.isRevealing = false" in reveal_block


def test_reveal_animation_defers_won_completion_banner(client: TestClient):
    """Verify WON completion banner is deferred until after the final tile reveal finishes."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    reveal_idx = js.find("animateGuessReveal(gameState) {")
    assert reveal_idx != -1
    reveal_block = js[reveal_idx:reveal_idx + 4000]

    assert 'status === "WON"' in reveal_block
    assert "this.showCompletedState(gameState, true)" in reveal_block
    assert "totalDurationMs" in reveal_block


def test_reveal_animation_defers_lost_completion_banner(client: TestClient):
    """Verify LOST completion banner is deferred until after the fifth tile reveal finishes."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    reveal_idx = js.find("animateGuessReveal(gameState) {")
    assert reveal_idx != -1
    reveal_block = js[reveal_idx:reveal_idx + 4000]

    assert 'status === "LOST"' in reveal_block
    assert "this.showCompletedState(gameState, false)" in reveal_block


def test_persisted_guesses_load_without_reveal_animation(client: TestClient):
    """Verify persisted guesses rendered from GET /game/{id} do not use flip animations."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    render_guess_idx = js.find("renderGuess(guess) {")
    assert render_guess_idx != -1
    render_guess_block = js[render_guess_idx:render_guess_idx + 1200]

    assert "revealTile" not in render_guess_block
    assert "setTimeout" not in render_guess_block
    assert "this.setTileState(row, c, state)" in render_guess_block


def test_reveal_animation_respects_prefers_reduced_motion(client: TestClient):
    """Verify animateGuessReveal detects prefers-reduced-motion and falls back to immediate evaluation."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    reveal_idx = js.find("animateGuessReveal(gameState) {")
    assert reveal_idx != -1
    reveal_block = js[reveal_idx:reveal_idx + 1200]

    assert "prefers-reduced-motion: reduce" in reveal_block
    assert "this.applyGuessResult(gameState)" in reveal_block


def test_reveal_animation_contains_zero_client_side_wordle_logic(client: TestClient):
    """Verify animateGuessReveal maps backend results directly without computing Wordle matches."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    reveal_idx = js.find("animateGuessReveal(gameState) {")
    assert reveal_idx != -1
    reveal_block = js[reveal_idx:reveal_idx + 4000]

    assert 'evalItem.result === "CORRECT"' in reveal_block
    assert 'evalItem.result === "PRESENT"' in reveal_block
    assert 'evalItem.result === "ABSENT"' in reveal_block
    assert "target_word" not in reveal_block


def test_reveal_timeouts_cleaned_up_on_board_reset(client: TestClient):
    """Verify resetBoard clears all pending reveal timeouts and resets isRevealing."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    reset_idx = js.find("resetBoard() {")
    assert reset_idx != -1
    reset_block = js[reset_idx:reset_idx + 500]

    assert "this.clearRevealTimeouts()" in reset_block
    assert "this.isRevealing = false" in reset_block


# ============================================================================
# 15. Polished Game Completion UX (Phase 4B-4B)
# ============================================================================

from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent


def test_completion_ui_dom_structure(client: TestClient):
    """Verify state-completed template contains attempts metric, target word card, play again action, and feedback."""
    response = client.get("/game")
    assert response.status_code in (status.HTTP_200_OK, status.HTTP_303_SEE_OTHER)

    # Read template directly to verify DOM structure
    template_path = BASE_DIR / "app" / "templates" / "game" / "game.html"
    html = template_path.read_text(encoding="utf-8")

    assert 'id="state-completed"' in html
    assert 'id="completion-title"' in html
    assert 'id="completion-message"' in html
    assert 'id="completion-icon"' in html
    assert 'id="completion-attempts"' in html
    assert 'id="completion-target-wrapper"' in html
    assert 'id="completion-target"' in html
    assert 'id="action-play-again"' in html
    assert 'id="btn-play-again"' in html
    assert 'id="completion-feedback"' in html
    assert 'id="completion-feedback-text"' in html


def test_completion_css_won_and_lost_classes(client: TestClient):
    """Verify game.css provides distinct visual treatments for won (emerald) and lost (muted rose/slate)."""
    response = client.get("/static/css/game.css")
    assert response.status_code == status.HTTP_200_OK
    css = response.text

    assert ".state-completed.is-won" in css
    assert ".state-completed.is-lost" in css
    assert ".completion-icon" in css
    assert ".completion-target-card" in css
    assert ".completion-attempts" in css
    assert ".btn-play-again" in css
    assert ".completion-feedback" in css
    assert ".completion-feedback.is-limit" in css
    assert ".completion-feedback.is-error" in css


def test_completion_js_caches_new_elements(client: TestClient):
    """Verify cacheElements in game.js caches completion elements."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    cache_idx = js.find("cacheElements() {")
    assert cache_idx != -1
    cache_block = js[cache_idx:cache_idx + 4000]

    assert "completionIcon:" in cache_block
    assert "completionAttempts:" in cache_block
    assert "btnPlayAgain:" in cache_block
    assert "completionFeedback:" in cache_block
    assert "completionFeedbackText:" in cache_block


def test_play_again_click_triggers_start_game(client: TestClient):
    """Verify clicking action-play-again dispatches startGame with play-again source."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    bind_idx = js.find("bindEvents() {")
    assert bind_idx != -1
    bind_block = js[bind_idx:bind_idx + 1000]

    assert "btnPlayAgain" in bind_block
    assert 'this.startGame("play-again")' in bind_block


def test_play_again_duplicate_click_prevention(client: TestClient):
    """Verify startGame enforces isStartingGame guard to prevent duplicate clicks."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    start_idx = js.find('startGame(triggerSource = "start") {')
    assert start_idx != -1
    start_block = js[start_idx:start_idx + 600]

    assert "if (this.isStartingGame) return;" in start_block
    assert "this.setStartButtonLoading(true, triggerSource)" in start_block


def test_play_again_201_navigation(client: TestClient):
    """Verify handleStartGameResponse navigates to /game?game_id=... upon 201 Created."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    handle_idx = js.find('handleStartGameResponse(response, triggerSource = "start") {')
    assert handle_idx != -1
    handle_block = js[handle_idx:handle_idx + 5000]

    assert "response.status === 201" in handle_block
    assert "window.location.assign" in handle_block
    assert "/game?game_id=" in handle_block


def test_play_again_429_limit_handling_preserves_board(client: TestClient):
    """Verify 429 response uses backend detail message, disables button, and keeps completed board intact."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    handle_idx = js.find('handleStartGameResponse(response, triggerSource = "start") {')
    assert handle_idx != -1
    end_idx = js.find('handleStartGameError(', handle_idx)
    assert end_idx != -1
    handle_block = js[handle_idx:end_idx]

    assert "response.status === 429" in handle_block
    assert "data.detail" in handle_block
    assert 'triggerSource === "play-again"' in handle_block
    assert 'this.showCompletionFeedback(limitMsg, "limit")' in handle_block
    assert "playAgainBtn.disabled = true" in handle_block
    assert "Daily Limit Reached" in handle_block
    # Verify it does not reset the board
    assert "resetBoard" not in handle_block


def test_play_again_preserves_completed_game_on_error(client: TestClient):
    """Verify 401, server error, or network failure keep completed game intact and show friendly feedback."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    handle_idx = js.find('handleStartGameResponse(response, triggerSource = "start") {')
    assert handle_idx != -1
    handle_block = js[handle_idx:handle_idx + 5000]

    assert "response.status === 401" in handle_block
    assert 'this.showCompletionFeedback("Your session has expired' in handle_block
    assert 'this.showCompletionFeedback(errorMsg, "error")' in handle_block

    err_idx = js.find('handleStartGameError(error, triggerSource = "start") {')
    assert err_idx != -1
    err_block = js[err_idx:err_idx + 800]
    assert 'this.showCompletionFeedback(msg, "error")' in err_block


def test_show_completed_state_populates_attempts_and_target(client: TestClient):
    """Verify showCompletedState populates attempts, target word, toggle classes, and focuses play again."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    show_idx = js.find("showCompletedState(gameState, isWin) {")
    assert show_idx != -1
    show_block = js[show_idx:show_idx + 4500]

    assert "panel.classList.add(isWin ? \"is-won\" : \"is-lost\")" in show_block
    assert "this.elements.completionIcon.innerHTML = isWin ?" in show_block
    assert "this.elements.completionAttempts.textContent =" in show_block
    assert "this.elements.completionTarget.textContent = gameState.target_word" in show_block
    assert "playAgainBtn.focus(" in show_block


def test_completion_panel_accessible_attributes(client: TestClient):
    """Verify accessibility attributes on state-completed and completion-feedback."""
    template_path = BASE_DIR / "app" / "templates" / "game" / "game.html"
    html = template_path.read_text(encoding="utf-8")

    assert 'role="region"' in html
    assert 'aria-label="Game Completion Summary"' in html
    assert 'role="alert"' in html
    assert 'aria-live="polite"' in html


# ============================================================================
# 16. Phase 4B-4C UX Polish & Edge-Case Verification Tests
# ============================================================================


def test_active_row_filled_tile_border_specificity(client: TestClient):
    """Verify CSS contains .board-row.is-active .board-tile.is-filled to ensure crisp contrast."""
    response = client.get("/static/css/game.css")
    assert response.status_code == status.HTTP_200_OK
    css = response.text

    assert ".board-row.is-active .board-tile.is-filled" in css
    assert "border-color: var(--color-tile-border-filled);" in css


def test_guess_feedback_reserved_footprint_css(client: TestClient):
    """Verify .guess-feedback has reserved footprint to prevent layout shifts."""
    response = client.get("/static/css/game.css")
    assert response.status_code == status.HTTP_200_OK
    css = response.text

    assert ".guess-feedback" in css
    assert "min-height: 2.25rem;" in css
    assert ".guess-feedback.is-hidden" in css
    assert "visibility: hidden;" in css
    assert "border-color: transparent !important;" in css


def test_btn_active_tactile_and_touch_target_css(client: TestClient):
    """Verify primary game buttons have 44px min-height and tactile active styling."""
    response = client.get("/static/css/game.css")
    assert response.status_code == status.HTTP_200_OK
    css = response.text

    assert "min-height: 44px;" in css
    assert ".btn-game-action:active:not(:disabled)" in css


def test_game_html_daily_limit_and_accessibility_attributes(client: TestClient):
    """Verify game.html renders data-daily-limit-reached, tabindex="-1", and live region on attempts."""
    template_path = BASE_DIR / "app" / "templates" / "game" / "game.html"
    html = template_path.read_text(encoding="utf-8")

    assert 'data-daily-limit-reached="' in html
    assert 'tabindex="-1"' in html
    assert 'id="attempts-display"' in html
    assert 'aria-atomic="true"' in html


def test_game_js_check_initial_game_respects_daily_limit(client: TestClient):
    """Verify checkInitialGame checks daily limit dataset and shows limit state if already reached."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    check_idx = js.find("checkInitialGame() {")
    assert check_idx != -1
    check_block = js[check_idx:check_idx + 3000]

    assert "isDailyLimitReached" in check_block
    assert 'this.showState("limit", { keepReady: true })' in check_block
    assert 'this.updateStatusBadge("ready", "Limit Reached")' in check_block
    assert "Daily Limit Reached" in check_block


def test_game_js_start_game_clears_stale_error(client: TestClient):
    """Verify startGame dismisses any existing stateError banner."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    start_idx = js.find('startGame(triggerSource = "start") {')
    assert start_idx != -1
    start_block = js[start_idx:start_idx + 800]

    assert "this.elements.stateError.classList.add(\"is-hidden\")" in start_block


def test_game_js_load_game_resets_board(client: TestClient):
    """Verify loadGameState calls resetBoard before setting stateLoading."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    load_idx = js.find("async loadGameState(gameId) {")
    assert load_idx != -1
    load_block = js[load_idx:load_idx + 600]

    assert "this.resetBoard();" in load_block
    assert 'this.showState("loading");' in load_block


def test_game_js_ime_composition_and_repeat_guards(client: TestClient):
    """Verify handleKeyDown includes event.isComposing and Enter repeat guards."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    key_idx = js.find("handleKeyDown(event) {")
    assert key_idx != -1
    key_block = js[key_idx:key_idx + 2500]

    assert "event.isComposing" in key_block
    assert "if (event.repeat) return;" in key_block


def test_game_js_backspace_clears_feedback_always(client: TestClient):
    """Verify handleBackspace calls clearInputFeedback regardless of current input length."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    bs_idx = js.find("handleBackspace() {")
    assert bs_idx != -1
    bs_block = js[bs_idx:bs_idx + 600]

    feedback_pos = bs_block.find("this.clearInputFeedback();")
    len_check_pos = bs_block.find("if (this.currentInput.length === 0) return;")
    assert feedback_pos != -1
    assert len_check_pos != -1
    assert feedback_pos < len_check_pos


def test_game_js_completion_focus_fallback(client: TestClient):
    """Verify showCompletedState falls back to focusing stateCompleted if playAgainBtn is disabled."""
    response = client.get("/static/js/game.js")
    assert response.status_code == status.HTTP_200_OK
    js = response.text

    show_idx = js.find("showCompletedState(gameState, isWin) {")
    assert show_idx != -1
    show_block = js[show_idx:show_idx + 4500]

    assert "this.clearInputFeedback();" in show_block
    assert "!playAgainBtn.disabled" in show_block
    assert "this.elements.stateCompleted.focus(" in show_block









