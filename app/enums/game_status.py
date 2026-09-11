import enum


class GameStatus(str, enum.Enum):
    """Game status enumeration."""

    IN_PROGRESS = "IN_PROGRESS"
    WON = "WON"
    LOST = "LOST"
