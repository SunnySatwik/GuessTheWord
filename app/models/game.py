from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime
from app.enums.game_status import GameStatus

if TYPE_CHECKING:
    from app.models.guess import Guess
    from app.models.user import User
    from app.models.word import Word


class Game(Base):
    """Game database model."""

    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    word_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("words.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[GameStatus] = mapped_column(
        Enum(GameStatus, native_enum=False, length=20),
        default=GameStatus.IN_PROGRESS,
        nullable=False,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime,
        nullable=True,
        default=None,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="games")
    word: Mapped["Word"] = relationship("Word", back_populates="games")
    guesses: Mapped[list["Guess"]] = relationship(
        "Guess",
        back_populates="game",
        cascade="all, delete-orphan",
        order_by="Guess.attempt_number",
    )
