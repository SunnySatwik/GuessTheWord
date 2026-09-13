from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.enums.role import UserRole
from app.models.user import User
from app.schemas.auth import validate_password, validate_username

# Password hashing configuration using Argon2id via pwdlib
password_hash_context = PasswordHash.recommended()

# Session serializer using the configured SECRET_KEY
session_serializer = URLSafeTimedSerializer(
    secret_key=settings.secret_key,
    salt="auth_session",
)

# Default session duration: 24 hours (in seconds)
SESSION_MAX_AGE = 86400
SESSION_COOKIE_NAME = "session_token"


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return password_hash_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2id hash."""
    return password_hash_context.verify(plain_password, hashed_password)


def create_session_token(user_id: int) -> str:
    """Generate a signed, timed session token containing user_id."""
    return session_serializer.dumps({"user_id": user_id})


def decode_session_token(token: str, max_age: int = SESSION_MAX_AGE) -> int | None:
    """Decode and verify a session token, returning the user_id or None if invalid/expired."""
    try:
        data = session_serializer.loads(token, max_age=max_age)
        return data.get("user_id")
    except (BadSignature, SignatureExpired, Exception):
        return None


def get_user_by_username(db: Session, username: str) -> User | None:
    """Retrieve a user by normalized username."""
    normalized = username.strip().lower() if username else ""
    return db.execute(select(User).where(User.username == normalized)).scalar_one_or_none()


def get_user_by_id(db: Session, user_id: int) -> User | None:
    """Retrieve a user by primary key ID."""
    return db.get(User, user_id)


def register_user(
    db: Session,
    username: str,
    password: str,
    role: UserRole = UserRole.PLAYER,
) -> User:
    """Register a new user with hashed password and default PLAYER role.

    Raises ValueError if username already exists.
    """
    normalized_username = username.strip().lower()

    # Check for existing user
    if get_user_by_username(db, normalized_username) is not None:
        raise ValueError("Username is already taken.")

    hashed_pw = hash_password(password)
    user = User(
        username=normalized_username,
        password_hash=hashed_pw,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    """Authenticate user with username and password.

    Returns the User if valid, None otherwise.
    """
    user = get_user_by_username(db, username)
    if not user:
        return None

    if not verify_password(password, user.password_hash):
        return None

    return user


def create_admin_account(
    db: Session,
    username: str,
    password: str,
    confirm_password: str | None = None,
) -> User:
    """Create a new user with ADMIN role after validating credentials.

    Validates:
    - Username length and format (via validate_username)
    - Password confirmation match (if confirm_password is provided)
    - Password complexity (via validate_password)
    - Uniqueness of username

    Hashes password using Argon2id and commits transaction.
    Rolls back transaction on failure.
    Raises ValueError on validation failure or if username is taken.
    """
    normalized_username = username.strip().lower() if username else ""

    valid_u, u_err = validate_username(normalized_username)
    if not valid_u:
        raise ValueError(u_err)

    if confirm_password is not None and password != confirm_password:
        raise ValueError("Passwords do not match.")

    valid_p, p_err = validate_password(password)
    if not valid_p:
        raise ValueError(p_err)

    if get_user_by_username(db, normalized_username) is not None:
        raise ValueError(f"Username '{normalized_username}' is already taken.")

    try:
        user = register_user(
            db=db,
            username=normalized_username,
            password=password,
            role=UserRole.ADMIN,
        )
        return user
    except Exception:
        db.rollback()
        raise

