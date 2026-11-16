from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient
from app.tool_executor.interfaces import ExecutionResult
from app.tool_registry.service import ToolRegistryService


@pytest.mark.asyncio
async def test_approval_api_full_lifecycle(test_client: AsyncClient, mock_db):
    # Seed default tools
    tool_service = ToolRegistryService(mock_db)
    await tool_service.seed_default_tools()

    # 1. Register and login test user
    await test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "developer@example.com",
            "password": "Password123!",
            "full_name": "Dev User",
            "role": "EMPLOYEE",
        },
    )
    login_resp = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "developer@example.com", "password": "Password123!"},
    )
    token = login_resp.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    # 2. Natural language task creation via POST /api/v1/ai/interpret
    command = "Create a task to implement JWT authentication in Spring Boot with high priority due next Friday"
    interpret_resp = await test_client.post(
        "/api/v1/ai/interpret",
        headers=auth_headers,
        json={"command": command},
    )
    assert interpret_resp.status_code == 200
    interpret_data = interpret_resp.json()
    assert interpret_data["intent"] == "create_card"
    assert interpret_data["approval_required"] is True
    preview = interpret_data["execution_preview"]
    assert preview is not None
    action_id = preview["action_id"]
    assert action_id.startswith("ACT-PREV-")
    assert preview["draft"]["priority"] == "HIGH"
    assert preview["draft"]["due_date"] == "next Friday"

    # 3. GET /api/v1/approvals/{action_id} - View draft preview
    get_resp = await test_client.get(f"/api/v1/approvals/{action_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["action_id"] == action_id
    assert get_data["status"] == "PENDING"
    assert "JWT" in get_data["draft"]["title"]

    # 4. PATCH /api/v1/approvals/{action_id} - Edit draft fields
    patch_resp = await test_client.patch(
        f"/api/v1/approvals/{action_id}",
        headers=auth_headers,
        json={
            "title": "Implement JWT authentication & OAuth2 in Spring Boot",
            "description": "Full security implementation with refresh tokens",
            "priority": "URGENT",
            "list_name": "In Progress",
        },
    )
    assert patch_resp.status_code == 200
    patch_data = patch_resp.json()
    assert patch_data["draft"]["title"] == "Implement JWT authentication & OAuth2 in Spring Boot"
    assert patch_data["draft"]["priority"] == "URGENT"
    assert patch_data["draft"]["list_name"] == "In Progress"

    # 5. POST /api/v1/approvals/{action_id}/confirm - Confirm and execute
    # Mock executor output for card creation
    mock_result = ExecutionResult(
        tool_id="trello_create_card",
        status="SUCCESS",
        is_mutation=True,
        result={
            "status": "SUCCESS",
            "action": "CREATED",
            "card": {
                "id": "trello_card_jwt_123",
                "name": "Implement JWT authentication & OAuth2 in Spring Boot",
                "url": "https://trello.com/c/jwt12345/implement-jwt",
                "shortUrl": "https://trello.com/c/jwt12345",
            },
        },
        message="Card successfully created on Trello",
    )

    with patch("app.tool_executor.service.ToolExecutorService.execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_result
        confirm_resp = await test_client.post(
            f"/api/v1/approvals/{action_id}/confirm",
            headers=auth_headers,
        )
        assert confirm_resp.status_code == 200
        confirm_data = confirm_resp.json()
        assert confirm_data["status"] == "EXECUTED"
        assert confirm_data["card_id"] == "trello_card_jwt_123"
        assert confirm_data["card_url"] == "https://trello.com/c/jwt12345/implement-jwt"

    # 6. Duplicate Confirmation attempt -> 409 Conflict (Race condition protection)
    dup_resp = await test_client.post(
        f"/api/v1/approvals/{action_id}/confirm",
        headers=auth_headers,
    )
    assert dup_resp.status_code == 409


@pytest.mark.asyncio
async def test_approval_api_cancel_flow(test_client: AsyncClient, mock_db):
    tool_service = ToolRegistryService(mock_db)
    await tool_service.seed_default_tools()

    # Register and login user
    await test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "cancel_user@example.com",
            "password": "Password123!",
            "full_name": "Cancel User",
            "role": "EMPLOYEE",
        },
    )
    login_resp = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "cancel_user@example.com", "password": "Password123!"},
    )
    token = login_resp.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    # Create task draft
    interpret_resp = await test_client.post(
        "/api/v1/ai/interpret",
        headers=auth_headers,
        json={"command": "Create task to test cancellation"},
    )
    action_id = interpret_resp.json()["execution_preview"]["action_id"]

    # Cancel action draft
    cancel_resp = await test_client.post(
        f"/api/v1/approvals/{action_id}/cancel",
        headers=auth_headers,
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "REJECTED"

    # Attempting to confirm cancelled action returns 409 Conflict
    confirm_resp = await test_client.post(
        f"/api/v1/approvals/{action_id}/confirm",
        headers=auth_headers,
    )
    assert confirm_resp.status_code == 409


@pytest.mark.asyncio
async def test_approval_api_security_and_authorization(test_client: AsyncClient, mock_db):
    tool_service = ToolRegistryService(mock_db)
    await tool_service.seed_default_tools()

    # User 1 (Owner)
    await test_client.post(
        "/api/v1/auth/register",
        json={"email": "owner@example.com", "password": "Password123!", "full_name": "Owner", "role": "EMPLOYEE"},
    )
    resp1 = await test_client.post("/api/v1/auth/login", json={"email": "owner@example.com", "password": "Password123!"})
    token1 = resp1.json()["access_token"]

    # User 2 (Other employee)
    await test_client.post(
        "/api/v1/auth/register",
        json={"email": "other@example.com", "password": "Password123!", "full_name": "Other", "role": "EMPLOYEE"},
    )
    resp2 = await test_client.post("/api/v1/auth/login", json={"email": "other@example.com", "password": "Password123!"})
    token2 = resp2.json()["access_token"]

    # Owner creates action draft
    interpret_resp = await test_client.post(
        "/api/v1/ai/interpret",
        headers={"Authorization": f"Bearer {token1}"},
        json={"command": "Create a task for confidential deployment"},
    )
    action_id = interpret_resp.json()["execution_preview"]["action_id"]

    # 1. Unauthenticated request -> 401 Unauthorized
    unauth_resp = await test_client.get(f"/api/v1/approvals/{action_id}")
    assert unauth_resp.status_code == 401

    # 2. Other user tries to GET draft -> 403 Forbidden
    other_get = await test_client.get(
        f"/api/v1/approvals/{action_id}",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert other_get.status_code == 403

    # 3. Other user tries to confirm -> 403 Forbidden
    other_confirm = await test_client.post(
        f"/api/v1/approvals/{action_id}/confirm",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert other_confirm.status_code == 403

    # 4. Other user tries to edit -> 403 Forbidden
    other_edit = await test_client.patch(
        f"/api/v1/approvals/{action_id}",
        headers={"Authorization": f"Bearer {token2}"},
        json={"title": "Hacked Title"},
    )
    assert other_edit.status_code == 403

    # 5. Invalid action ID -> 404 Not Found
    not_found_resp = await test_client.get(
        "/api/v1/approvals/ACT-PREV-NONEXISTENT",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert not_found_resp.status_code == 404

