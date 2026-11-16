import pytest
from httpx import AsyncClient
from app.core.config import settings
from app.tool_registry.service import ToolRegistryService


async def get_auth_headers(test_client: AsyncClient, mock_db, email="p7_user@example.com"):
    tool_service = ToolRegistryService(mock_db)
    await tool_service.seed_default_tools()
    await test_client.post(
        f"{settings.API_V1_PREFIX}/auth/register",
        json={"email": email, "password": "Password123!", "full_name": "Phase 7 User", "role": "ADMIN"},
    )
    login_resp = await test_client.post(
        f"{settings.API_V1_PREFIX}/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_conversational_task_creation_and_preview(test_client: AsyncClient, mock_db):
    headers = await get_auth_headers(test_client, mock_db, "user_conv1@example.com")

    # 1. Send natural language command to create a task
    resp = await test_client.post(
        f"{settings.API_V1_PREFIX}/ai/interpret",
        json={"command": "Create a task card Login API with JWT support"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["approval_required"] is True
    assert data["action_id"] is not None
    assert data["execution_preview"] is not None
    assert data["execution_preview"]["action_id"] == data["action_id"]
    assert "Login API" in data["execution_preview"]["draft"]["title"]
    assert data["execution_preview"]["status"] == "PENDING"
    action_id = data["action_id"]

    # 2. Conversational Edit: Change priority to High
    edit_resp = await test_client.post(
        f"{settings.API_V1_PREFIX}/ai/interpret",
        json={"command": "Change priority to High and add description for authentication flow", "active_action_id": action_id},
        headers=headers,
    )
    assert edit_resp.status_code == 200
    edit_data = edit_resp.json()
    assert edit_data["approval_required"] is True
    assert edit_data["action_id"] == action_id
    assert edit_data["execution_preview"]["draft"]["priority"] == "HIGH"

    # 3. Conversational Rejection: Cancel the action
    cancel_resp = await test_client.post(
        f"{settings.API_V1_PREFIX}/ai/interpret",
        json={"command": "cancel", "active_action_id": action_id},
        headers=headers,
    )
    assert cancel_resp.status_code == 200
    cancel_data = cancel_resp.json()
    assert cancel_data["intent"] == "cancel_action"
    assert "rejected" in cancel_data["conversational_message"].lower()


@pytest.mark.asyncio
async def test_conversational_read_operations_immediate(test_client: AsyncClient, mock_db):
    headers = await get_auth_headers(test_client, mock_db, "user_conv2@example.com")

    # Read operation: Search cards
    resp = await test_client.post(
        f"{settings.API_V1_PREFIX}/ai/interpret",
        json={"command": "search cards for Login"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["approval_required"] is False
    assert data["execution_result"] is not None
    assert "cards" in data["execution_result"]

    # Read operation: Workload report
    resp2 = await test_client.post(
        f"{settings.API_V1_PREFIX}/ai/interpret",
        json={"command": "show workload report"},
        headers=headers,
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["approval_required"] is False
    assert data2["execution_result"] is not None


@pytest.mark.asyncio
async def test_persistent_chat_history_api(test_client: AsyncClient, mock_db):
    headers = await get_auth_headers(test_client, mock_db, "user_conv3@example.com")

    # Send a message to populate history
    await test_client.post(
        f"{settings.API_V1_PREFIX}/ai/interpret",
        json={"command": "search cards for Database"},
        headers=headers,
    )

    # Fetch history
    resp = await test_client.get(f"{settings.API_V1_PREFIX}/ai/history", headers=headers)
    assert resp.status_code == 200
    history = resp.json()
    assert "messages" in history
    assert history["total"] >= 2  # user + assistant

    # Clear history
    resp_clear = await test_client.delete(f"{settings.API_V1_PREFIX}/ai/history", headers=headers)
    assert resp_clear.status_code == 200

    # Fetch history again (must be 0)
    resp_empty = await test_client.get(f"{settings.API_V1_PREFIX}/ai/history", headers=headers)
    assert resp_empty.status_code == 200
    assert resp_empty.json()["total"] == 0


@pytest.mark.asyncio
async def test_live_overview_and_activities_endpoints(test_client: AsyncClient, mock_db):
    headers = await get_auth_headers(test_client, mock_db, "user_conv4@example.com")

    # Overview stats
    ov_resp = await test_client.get(f"{settings.API_V1_PREFIX}/overview/stats", headers=headers)
    assert ov_resp.status_code == 200
    ov_data = ov_resp.json()
    assert "tasks" in ov_data
    assert "system" in ov_data
    assert "active_tools" in ov_data["system"]

    # Activities history
    act_resp = await test_client.get(f"{settings.API_V1_PREFIX}/activities", headers=headers)
    assert act_resp.status_code == 200
    act_data = act_resp.json()
    assert "activities" in act_data

    # Trello tasks
    tasks_resp = await test_client.get(f"{settings.API_V1_PREFIX}/tasks/trello", headers=headers)
    assert tasks_resp.status_code == 200
    tasks_data = tasks_resp.json()
    assert "cards" in tasks_data

    # Workload report
    rep_resp = await test_client.get(f"{settings.API_V1_PREFIX}/reports/workload", headers=headers)
    assert rep_resp.status_code == 200
    rep_data = rep_resp.json()
    assert "total_tasks" in rep_data
