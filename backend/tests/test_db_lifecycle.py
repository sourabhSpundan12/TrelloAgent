import pytest
from mongomock_motor import AsyncMongoMockClient
from app.db.mongodb import MongoDBManager


@pytest.mark.asyncio
async def test_mock_mongodb_lifecycle():
    # Use mongomock for testing without a live MongoDB server
    mock_client = AsyncMongoMockClient()
    MongoDBManager.client = mock_client
    MongoDBManager.db = mock_client["test_database"]

    # Verify ping
    is_alive = await MongoDBManager.ping()
    assert is_alive is True

    # Test ensuring indexes
    await MongoDBManager.ensure_indexes()

    # Clean up
    await MongoDBManager.disconnect()
    assert MongoDBManager.client is None
    assert MongoDBManager.db is None

