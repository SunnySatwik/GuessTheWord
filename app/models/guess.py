from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime

if TYPE_CHECKING:
    from app.models.game import Game


class Guess(Base):
    """Guess database model."""

    __tablename__ = "guesses"
    __table_args__ = (
        UniqueConstraint("game_id", "attempt_number", name="uq_game_attempt_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    guess: Mapped[str] = mapped_column(String(5), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationship: 1 Game -> N Guesses
    game: Mapped["Game"] = relationship(
        "Game",
        back_populates="guesses",
    )
