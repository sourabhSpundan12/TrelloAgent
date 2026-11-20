from unittest.mock import patch
import pytest
from httpx import AsyncClient
from app.database.mongodb import MongoDBManager


@pytest.mark.asyncio
async def test_health_endpoints(test_client: AsyncClient):
    with patch.object(MongoDBManager, "ping", return_value=True):
        resp = await test_client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert "uptime_seconds" in data
        assert "services" in data


@pytest.mark.asyncio
async def test_liveness_probe(test_client: AsyncClient):
    resp = await test_client.get("/api/v1/health/live")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "alive"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_readiness_probe_healthy(test_client: AsyncClient):
    with patch.object(MongoDBManager, "ping", return_value=True):
        resp = await test_client.get("/api/v1/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["database"] == "connected"


@pytest.mark.asyncio
async def test_readiness_probe_unhealthy(test_client: AsyncClient):
    with patch.object(MongoDBManager, "ping", return_value=False):
        resp = await test_client.get("/api/v1/health/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "not_ready"
        assert data["database"] == "disconnected"


@pytest.mark.asyncio
async def test_app_info_endpoint(test_client: AsyncClient):
    resp = await test_client.get("/api/v1/info")
    assert resp.status_code == 200
    data = resp.json()
    assert data["app_name"] == "PM Hooks"
    assert data["environment"] == "testing"
    assert data["api_prefix"] == "/api/v1"

