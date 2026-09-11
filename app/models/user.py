from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime
from app.enums.role import UserRole

if TYPE_CHECKING:
    from app.models.game import Game


class User(Base):
    """User database model."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=20),
        default=UserRole.PLAYER,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationship: 1 User -> N Games
    games: Mapped[list["Game"]] = relationship(
        "Game",
        back_populates="user",
        cascade="all, delete-orphan",
    )
