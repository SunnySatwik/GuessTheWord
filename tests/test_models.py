from datetime import datetime, timezone
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base
from app.enums.game_status import GameStatus
from app.enums.role import UserRole
from app.models import Game, Guess, User, Word


def test_models_importable():
    """1. Verify all four models can be imported and inherit from Base."""
    assert issubclass(User, Base)
    assert issubclass(Word, Base)
    assert issubclass(Game, Base)
    assert issubclass(Guess, Base)


def test_tables_created_in_test_db(db_session: Session):
    """2. Verify all four tables are created in the isolated test database."""
    expected_tables = {"users", "words", "games", "guesses"}
    assert expected_tables.issubset(Base.metadata.tables.keys())

    # Execute select queries on all four tables
    for model in (User, Word, Game, Guess):
        result = db_session.execute(select(model)).scalars().all()
        assert isinstance(result, list)


def test_create_user(db_session: Session):
    """3. Verify a User can be created with expected defaults and timezone-aware timestamp."""
    user = User(
        username="alice",
        password_hash="hashed_pw_placeholder",
        role=UserRole.PLAYER,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    assert user.id is not None
    assert user.username == "alice"
    assert user.role == UserRole.PLAYER
    assert user.created_at is not None
    assert user.created_at.tzinfo is not None


def test_create_word(db_session: Session):
    """4. Verify a Word can be created with expected fields and timezone-aware timestamp."""
    word = Word(word="REACT")
    db_session.add(word)
    db_session.commit()
    db_session.refresh(word)

    assert word.id is not None
    assert word.word == "REACT"
    assert word.created_at is not None
    assert word.created_at.tzinfo is not None


def test_game_references_user_and_word(db_session: Session):
    """5. Verify a Game correctly references a User and Word."""
    user = User(username="bob", password_hash="bob_hash", role=UserRole.PLAYER)
    word = Word(word="PLANT")
    db_session.add_all([user, word])
    db_session.commit()

    game = Game(user_id=user.id, word_id=word.id)
    db_session.add(game)
    db_session.commit()
    db_session.refresh(game)

    assert game.id is not None
    assert game.user_id == user.id
    assert game.word_id == word.id


def test_guess_references_game(db_session: Session):
    """6. Verify a Guess correctly references a Game."""
    user = User(username="carol", password_hash="carol_hash")
    word = Word(word="CLOUD")
    db_session.add_all([user, word])
    db_session.commit()

    game = Game(user_id=user.id, word_id=word.id)
    db_session.add(game)
    db_session.commit()

    guess = Guess(game_id=game.id, guess="CRANE", attempt_number=1)
    db_session.add(guess)
    db_session.commit()
    db_session.refresh(guess)

    assert guess.id is not None
    assert guess.game_id == game.id
    assert guess.guess == "CRANE"
    assert guess.attempt_number == 1
    assert guess.created_at is not None
    assert guess.created_at.tzinfo is not None


def test_relationships_bidirectional(db_session: Session):
    """7. Verify relationships work in both directions across all models."""
    user = User(username="dave", password_hash="dave_hash")
    word = Word(word="SWIFT")
    db_session.add_all([user, word])
    db_session.commit()

    game = Game(user=user, word=word)
    db_session.add(game)
    db_session.commit()

    guess = Guess(game=game, guess="SHINE", attempt_number=1)
    db_session.add(guess)
    db_session.commit()

    # Refresh entities to check bidirectional relationships
    db_session.refresh(user)
    db_session.refresh(word)
    db_session.refresh(game)
    db_session.refresh(guess)

    # User -> Game -> User
    assert game in user.games
    assert game.user == user

    # Word -> Game -> Word
    assert game in word.games
    assert game.word == word

    # Game -> Guess -> Game
    assert guess in game.guesses
    assert guess.game == game


def test_user_username_uniqueness(db_session: Session):
    """8. Verify User.username uniqueness constraint is enforced."""
    user1 = User(username="unique_user", password_hash="hash1")
    db_session.add(user1)
    db_session.commit()

    user2 = User(username="unique_user", password_hash="hash2")
    db_session.add(user2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_word_word_uniqueness(db_session: Session):
    """9. Verify Word.word uniqueness constraint is enforced."""
    word1 = Word(word="STONE")
    db_session.add(word1)
    db_session.commit()

    word2 = Word(word="STONE")
    db_session.add(word2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_guess_attempt_number_uniqueness_within_game(db_session: Session):
    """10. Verify Guess attempt_number uniqueness within a single game is enforced."""
    user = User(username="eve", password_hash="eve_hash")
    word = Word(word="FLAME")
    db_session.add_all([user, word])
    db_session.commit()

    game1 = Game(user_id=user.id, word_id=word.id)
    game2 = Game(user_id=user.id, word_id=word.id)
    db_session.add_all([game1, game2])
    db_session.commit()

    # First guess in game1 (attempt 1)
    guess1 = Guess(game_id=game1.id, guess="FLOAT", attempt_number=1)
    db_session.add(guess1)
    db_session.commit()

    # Duplicate attempt 1 in the SAME game must fail
    duplicate_guess = Guess(game_id=game1.id, guess="FLEET", attempt_number=1)
    db_session.add(duplicate_guess)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # However, attempt 1 in a DIFFERENT game is valid
    guess_in_other_game = Guess(game_id=game2.id, guess="FLEET", attempt_number=1)
    db_session.add(guess_in_other_game)
    db_session.commit()
    assert guess_in_other_game.id is not None


def test_game_nullable_completed_at(db_session: Session):
    """11. Verify completed_at is nullable on game creation and can be set upon completion."""
    user = User(username="frank", password_hash="frank_hash")
    word = Word(word="BRAIN")
    db_session.add_all([user, word])
    db_session.commit()

    game = Game(user_id=user.id, word_id=word.id)
    db_session.add(game)
    db_session.commit()
    db_session.refresh(game)

    assert game.completed_at is None

    # Update completed_at
    completion_time = datetime.now(timezone.utc)
    game.completed_at = completion_time
    game.status = GameStatus.WON
    db_session.commit()
    db_session.refresh(game)

    assert game.completed_at is not None
    assert game.completed_at.tzinfo is not None
    assert game.status == GameStatus.WON


def test_game_defaults(db_session: Session):
    """12. Verify default status (IN_PROGRESS), attempts (0), and started_at on Game."""
    user = User(username="grace", password_hash="grace_hash")
    word = Word(word="OCEAN")
    db_session.add_all([user, word])
    db_session.commit()

    game = Game(user_id=user.id, word_id=word.id)
    db_session.add(game)
    db_session.commit()
    db_session.refresh(game)

    assert game.status == GameStatus.IN_PROGRESS
    assert game.attempts == 0
    assert game.started_at is not None
    assert game.started_at.tzinfo is not None


def test_foreign_key_enforcement(db_session: Session):
    """Verify that referencing non-existent foreign keys fails due to SQLite foreign key constraints."""
    # Attempt to create a Game with an invalid user_id
    invalid_game = Game(user_id=99999, word_id=99999)
    db_session.add(invalid_game)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
