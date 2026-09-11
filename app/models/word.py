from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime

if TYPE_CHECKING:
    from app.models.game import Game


class Word(Base):
    """Word database model."""

    __tablename__ = "words"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String(5), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationship: 1 Word -> N Games
    games: Mapped[list["Game"]] = relationship(
        "Game",
        back_populates="word",
    )
