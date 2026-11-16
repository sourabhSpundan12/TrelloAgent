import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root_endpoint(test_client: AsyncClient):
    response = await test_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "version" in data
    assert data["docs"] == "/docs"
    assert data["health"] == "/health"


@pytest.mark.asyncio
async def test_root_health_endpoint(test_client: AsyncClient):
    response = await test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert "version" in data
    assert "database" in data
    assert "uptime_seconds" in data
    assert "services" in data
    assert isinstance(data["services"]["gemini_configured"], bool)
    assert isinstance(data["services"]["trello_configured"], bool)
    assert isinstance(data["services"]["n8n_configured"], bool)


@pytest.mark.asyncio
async def test_api_v1_health_endpoint(test_client: AsyncClient):
    response = await test_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert data["environment"] == "testing"

