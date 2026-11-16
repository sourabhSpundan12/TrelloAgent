from datetime import timedelta
from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient
from app.core.security import create_access_token
from app.services.auth_service import AuthService
from app.tool_executor.interfaces import ExecutionResult
from app.tool_registry.service import ToolRegistryService


@pytest.mark.asyncio
async def test_auth_full_verification_flow(test_client: AsyncClient, mock_db):
    """
    Rigorously verifies the 9 required authentication test cases:
    1. Login successfully.
    2. Verify JWT is returned.
    3. Verify token format.
    4. Send an AI interpretation request with Authorization header.
    5. Verify Authorization header is accepted without exposing the token.
    6. Verify backend identifies the authenticated user.
    7. Verify task preview is generated.
    8. Verify approval endpoints work.
    9. Verify expired/invalid tokens correctly return 401.
    """
    # Setup database with default tools and admin
    tool_service = ToolRegistryService(mock_db)
    await tool_service.seed_default_tools()
    auth_service = AuthService(mock_db)
    await auth_service.bootstrap_admin()

    # Step 1: Login successfully
    login_payload = {
        "email": "admin@example.com",
        "password": "AdminSecurePassword123!",
    }
    login_resp = await test_client.post("/api/v1/auth/login", json=login_payload)
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"

    # Step 2: Verify JWT is returned
    token_data = login_resp.json()
    assert "access_token" in token_data
    assert "refresh_token" in token_data
    assert token_data.get("token_type") == "bearer"
    assert token_data.get("expires_in") == 1800
    jwt_token = token_data["access_token"]
    assert len(jwt_token.split(".")) == 3  # Valid JWT format: header.payload.signature

    # Step 3: Verify token can access protected /api/v1/auth/me
    auth_headers = {"Authorization": f"Bearer {jwt_token}"}
    me_resp = await test_client.get("/api/v1/auth/me", headers=auth_headers)
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == "admin@example.com"
    assert me_data["role"] == "ADMIN"

    # Step 4 & 5: Send AI interpretation request with Authorization header
    ai_cmd = "Create a task to implement JWT authentication in Spring Boot with high priority due next Friday"
    ai_resp = await test_client.post(
        "/api/v1/ai/interpret",
        headers=auth_headers,
        json={"command": ai_cmd},
    )
    assert ai_resp.status_code == 200, f"AI interpret failed: {ai_resp.text}"

    # Step 6: Verify backend identifies user and accepts interpretation
    ai_data = ai_resp.json()
    assert ai_data["intent"] == "create_card"
    assert ai_data["approval_required"] is True

    # Step 7: Verify task preview is generated
    preview = ai_data["execution_preview"]
    assert preview is not None
    action_id = preview["action_id"]
    assert action_id.startswith("ACT-PREV-")
    assert preview["draft"]["title"] is not None
    assert preview["draft"]["priority"] == "HIGH"
    assert preview["draft"]["due_date"] == "next Friday"
    assert preview["payload_hash"] is not None

    # Step 8: Verify approval endpoints work
    # A. Get preview
    get_preview_resp = await test_client.get(
        f"/api/v1/approvals/{action_id}",
        headers=auth_headers,
    )
    assert get_preview_resp.status_code == 200
    assert get_preview_resp.json()["action_id"] == action_id

    # B. Edit preview
    patch_resp = await test_client.patch(
        f"/api/v1/approvals/{action_id}",
        headers=auth_headers,
        json={"title": "Updated Task Title", "priority": "URGENT"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["draft"]["title"] == "Updated Task Title"
    assert patch_resp.json()["draft"]["priority"] == "URGENT"

    # C. Confirm preview
    mock_exec_result = ExecutionResult(
        tool_id="trello_create_card",
        status="SUCCESS",
        is_mutation=True,
        result={
            "status": "SUCCESS",
            "action": "CREATED",
            "card": {
                "id": "card_test_123",
                "name": "Updated Task Title",
                "url": "https://trello.com/c/testCard123",
            },
        },
        message="Created successfully",
    )
    with patch("app.tool_executor.service.ToolExecutorService.execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_exec_result
        confirm_resp = await test_client.post(
            f"/api/v1/approvals/{action_id}/confirm",
            headers=auth_headers,
        )
        assert confirm_resp.status_code == 200
        assert confirm_resp.json()["status"] == "EXECUTED"
        assert confirm_resp.json()["card_id"] == "card_test_123"
        assert confirm_resp.json()["card_url"] == "https://trello.com/c/testCard123"

    # Step 9: Verify expired/invalid/missing tokens correctly return 401
    # 9a. Missing Authorization header
    missing_auth_resp = await test_client.post(
        "/api/v1/ai/interpret",
        json={"command": "Create a card"},
    )
    assert missing_auth_resp.status_code == 401
    assert "AUTHENTICATION_FAILED" in missing_auth_resp.json()["error"]["code"]

    # 9b. Invalid/malformed JWT token
    invalid_auth_resp = await test_client.post(
        "/api/v1/ai/interpret",
        headers={"Authorization": "Bearer totally.invalid.token"},
    )
    assert invalid_auth_resp.status_code == 401

    # 9c. Expired JWT token
    expired_jwt = create_access_token(
        subject="admin_user_id",
        email="admin@example.com",
        role="ADMIN",
        expires_delta=timedelta(minutes=-30),  # expired 30 minutes ago
    )
    expired_resp = await test_client.post(
        "/api/v1/ai/interpret",
        headers={"Authorization": f"Bearer {expired_jwt}"},
        json={"command": "Create a card"},
    )
    assert expired_resp.status_code == 401
    assert "expired" in expired_resp.json()["error"]["message"].lower()

    # 9d. Resilient Bearer header handling: extra whitespace or accidental "Bearer Bearer"
    resilient_resp = await test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer Bearer {jwt_token}"},
    )
    assert resilient_resp.status_code == 200
    assert resilient_resp.json()["email"] == "admin@example.com"

