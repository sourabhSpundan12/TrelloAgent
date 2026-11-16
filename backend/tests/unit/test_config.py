from unittest.mock import patch
from app.core.config import Settings


def test_settings_default_values():
    settings = Settings(
        JWT_SECRET_KEY="test-secret-key-at-least-32-chars-long!",
        MONGODB_DATABASE="test_db",
    )
    assert settings.PROJECT_NAME == "Agentic Task Manager"
    assert settings.API_V1_STR == "/api/v1"
    assert settings.JWT_ALGORITHM == "HS256"
    assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 30
    assert settings.REFRESH_TOKEN_EXPIRE_DAYS == 7


def test_settings_cors_parsing():
    settings = Settings(
        JWT_SECRET_KEY="test-secret-key-at-least-32-chars-long!",
        BACKEND_CORS_ORIGINS=["http://localhost:3000", "http://localhost:5173"],
    )
    assert "http://localhost:3000" in settings.BACKEND_CORS_ORIGINS
    assert "http://localhost:5173" in settings.BACKEND_CORS_ORIGINS
