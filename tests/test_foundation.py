from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.main import app


def test_app_startup():
    """Verify application startup configuration and settings."""
    assert app.title == settings.app_name
    assert settings.app_name == "Guess the Word"
    assert settings.database_url is not None


def test_health_endpoint(client: TestClient):
    """Verify GET /health returns 200 and expected status payload."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == settings.app_name
    assert data["environment"] == settings.app_env


def test_root_endpoint(client: TestClient):
    """Verify GET / returns 200 HTML page confirming application is running."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "Guess the Word" in response.text
    assert "Welcome to Guess the Word" in response.text


def test_static_files_accessible(client: TestClient):
    """Verify mounted static assets are served properly."""
    response = client.get("/static/css/base.css")
    assert response.status_code == 200
    assert "text/css" in response.headers.get("content-type", "")
    assert "--bg-primary" in response.text


def test_database_session(db_session: Session):
    """Verify SQLAlchemy 2.x session can execute queries."""
    result = db_session.execute(text("SELECT 1")).scalar()
    assert result == 1
