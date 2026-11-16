import os
import sys
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
import mongomock_motor

# Ensure backend directory is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.database.mongodb import MongoDBManager, get_database
from app.main import app


@pytest.fixture(autouse=True)
def override_settings():
    settings.APP_ENV = "testing"
    settings.DEBUG = True
    settings.MONGODB_DATABASE = "agentic_task_manager_test"
    orig_gemini_key = settings.GEMINI_API_KEY
    orig_openai_key = settings.OPENAI_API_KEY
    settings.GEMINI_API_KEY = ""
    settings.OPENAI_API_KEY = ""
    yield
    settings.GEMINI_API_KEY = orig_gemini_key
    settings.OPENAI_API_KEY = orig_openai_key
    settings.APP_ENV = "development"


@pytest_asyncio.fixture(loop_scope="function")
async def mock_db():
    mock_client = mongomock_motor.AsyncMongoMockClient()
    db = mock_client["agentic_task_manager_test"]

    # Save original MongoDBManager state
    orig_client = MongoDBManager.client
    orig_db = MongoDBManager.db
    MongoDBManager.client = mock_client
    MongoDBManager.db = db

    # Override FastAPI database dependency
    app.dependency_overrides[get_database] = lambda: db

    yield db

    # Restore original state
    app.dependency_overrides.pop(get_database, None)
    MongoDBManager.client = orig_client
    MongoDBManager.db = orig_db


@pytest_asyncio.fixture(loop_scope="function")
async def test_client(mock_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
