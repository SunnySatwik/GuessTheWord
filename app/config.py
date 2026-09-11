from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory of the project (root level)
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    app_name: str = "Guess the Word"
    app_env: str = "development"
    debug: bool = False
    host: str = "127.0.0.1"
    port: int = 8000
    secret_key: str = "dev-insecure-secret-key-change-in-production"
    database_url: str = "sqlite:///./data/guesstheword.db"

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Global application settings instance
settings = Settings()
