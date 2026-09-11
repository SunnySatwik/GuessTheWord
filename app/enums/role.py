import enum


class UserRole(str, enum.Enum):
    """User role enumeration for access control."""

    PLAYER = "PLAYER"
    ADMIN = "ADMIN"
