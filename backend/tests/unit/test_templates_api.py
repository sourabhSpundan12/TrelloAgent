import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database.mongodb import get_database
from app.core.dependencies import get_current_user
from app.schemas.user import UserResponse


@pytest.mark.asyncio
async def test_templates_api_list():
    mock_db = MagicMock()
    mock_cursor = MagicMock()

    async def async_empty_iter():
        if False:
            yield {}

    mock_cursor.__aiter__ = lambda self: async_empty_iter()
    mock_cursor.sort.return_value = mock_cursor
    mock_db.__getitem__.return_value.find.return_value = mock_cursor

    mock_user = UserResponse(
        id="usr-test-1",
        email="test@domain.com",
        full_name="Test User",
        role="ADMIN",
        department="Engineering",
        is_active=True,
        created_at="2026-01-01T00:00:00Z",
    )

    app.dependency_overrides[get_database] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(
                "/api/v1/templates",
                headers={"Authorization": "Bearer fake_token"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SUCCESS"
        assert "templates" in data
        assert data["total"] >= 10
        template_ids = [t["id"] for t in data["templates"]]
        assert "tmpl_backend" in template_ids
        assert "tmpl_auth" in template_ids
        assert "tmpl_frontend" in template_ids
    finally:
        app.dependency_overrides.pop(get_database, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_templates_api_create_and_delete():
    mock_db = MagicMock()
    mock_col = MagicMock()
    mock_db.__getitem__.return_value = mock_col
    mock_col.insert_one = AsyncMock()
    mock_col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))

    mock_user = UserResponse(
        id="usr-test-1",
        email="test@domain.com",
        full_name="Test User",
        role="ADMIN",
        department="Engineering",
        is_active=True,
        created_at="2026-01-01T00:00:00Z",
    )

    app.dependency_overrides[get_database] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Create
            payload = {
                "name": "Payment Gateway",
                "category": "PAYMENT",
                "keywords": ["stripe", "payment"],
                "description_template": "Integrate payments for '{title}'.",
            }
            create_res = await ac.post(
                "/api/v1/templates",
                json=payload,
                headers={"Authorization": "Bearer fake_token"},
            )
            assert create_res.status_code == 201
            create_data = create_res.json()
            assert create_data["status"] == "SUCCESS"
            assert create_data["template"]["name"] == "Payment Gateway"
            tmpl_id = create_data["template"]["id"]

            # Delete
            del_res = await ac.delete(
                f"/api/v1/templates/{tmpl_id}",
                headers={"Authorization": "Bearer fake_token"},
            )
            assert del_res.status_code == 200
            del_data = del_res.json()
            assert del_data["status"] == "SUCCESS"
            assert del_data["deleted_id"] == tmpl_id
    finally:
        app.dependency_overrides.pop(get_database, None)
        app.dependency_overrides.pop(get_current_user, None)
