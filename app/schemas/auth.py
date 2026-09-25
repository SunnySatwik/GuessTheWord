import re
from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.enums.role import UserRole

# Allowed special characters as specified in requirements: $, %, *
ALLOWED_SPECIAL_CHARS = {"$", "%", "*"}


def validate_username(username: str) -> tuple[bool, str]:
    """Validate username according to specification:
    - At least 5 letters
    - Letters only (both upper and lower case accepted)
    """
    cleaned = username.strip() if username else ""
    if len(cleaned) < 5:
        return False, "Username must be at least 5 characters long."

    if not cleaned.isalpha():
        return False, "Username must contain only alphabetic letters."

    return True, ""


def validate_password(password: str) -> tuple[bool, str]:
    """Validate password according to specification:

    - At least 5 characters
    - Must contain alphabetic characters
    - Must contain numeric characters
    - Must contain at least one of $, %, *
    """
    if not password or len(password) < 5:
        return False, "Password must be at least 5 characters long."

    if not re.search(r"[a-zA-Z]", password):
        return False, "Password must contain at least one alphabetic character."

    if not re.search(r"[0-9]", password):
        return False, "Password must contain at least one numeric character."

    if not any(char in ALLOWED_SPECIAL_CHARS for char in password):
        return False, "Password must contain at least one of the following special characters: $, %, *"

    return True, ""


class UserRegisterSchema(BaseModel):
    """Schema for user registration."""

    username: str
    password: str
    confirm_password: str | None = None

    @field_validator("username")
    @classmethod
    def check_username(cls, v: str) -> str:
        valid, msg = validate_username(v)
        if not valid:
            raise ValueError(msg)
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        valid, msg = validate_password(v)
        if not valid:
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def check_passwords_match(self) -> "UserRegisterSchema":
        if self.confirm_password is not None and self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class UserLoginSchema(BaseModel):
    """Schema for user login."""

    username: str
    password: str

    @field_validator("username")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        return v.strip().lower()


class UserResponseSchema(BaseModel):
    """Public user response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: UserRole
    created_at: datetime
