import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ai_interpret_endpoint_flow(test_client: AsyncClient):
    # 1. Register & login user
    await test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "ai_user@example.com",
            "password": "Password123!",
            "full_name": "AI User",
            "role": "EMPLOYEE",
        },
    )
    login_resp = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "ai_user@example.com", "password": "Password123!"},
    )
    token = login_resp.json()["access_token"]

    # 2. Authentication required
    unauth_resp = await test_client.post(
        "/api/v1/ai/interpret",
        json={"command": "Create a card named Setup CI"},
    )
    assert unauth_resp.status_code == 401

    # 3. Valid command: Card creation
    create_resp = await test_client.post(
        "/api/v1/ai/interpret",
        headers={"Authorization": f"Bearer {token}"},
        json={"command": "Create a card named Setup CI"},
    )
    assert create_resp.status_code == 200
    create_data = create_resp.json()
    assert create_data["intent"] == "create_card"
    assert "Setup CI" in create_data["parameters"].get("name", "")
    assert create_data["selected_tool_id"] in ["trello_create_card", "trello_move_card"]
    assert create_data["approval_required"] is True
    assert create_data["execution_preview"] is not None
    assert create_data["execution_preview"]["payload_hash"] is not None
    assert create_data["requires_clarification"] is False

    # 4. Valid command: Card movement
    move_resp = await test_client.post(
        "/api/v1/ai/interpret",
        headers={"Authorization": f"Bearer {token}"},
        json={"command": "Move Setup CI card to IN_PROGRESS"},
    )
    assert move_resp.status_code == 200
    move_data = move_resp.json()
    assert move_data["intent"] == "move_card"
    assert move_data["parameters"].get("target_status") == "IN_PROGRESS"
    assert move_data["approval_required"] is True

    # 5. Read-only command: Workload report (no approval required)
    workload_resp = await test_client.post(
        "/api/v1/ai/interpret",
        headers={"Authorization": f"Bearer {token}"},
        json={"command": "Show me the workload report for today"},
    )
    assert workload_resp.status_code == 200
    workload_data = workload_resp.json()
    assert workload_data["intent"] == "get_workload"
    assert workload_data["approval_required"] is False
    assert workload_data["execution_preview"] is None

    # 6. Ambiguous command
    ambiguous_resp = await test_client.post(
        "/api/v1/ai/interpret",
        headers={"Authorization": f"Bearer {token}"},
        json={"command": "xyz qwerty random meaningless phrase 999"},
    )
    assert ambiguous_resp.status_code == 200
    amb_data = ambiguous_resp.json()
    assert amb_data["requires_clarification"] is True
    assert amb_data["clarification_message"] is not None

    # 7. Session lifecycle and multi-session isolation
    session_id_1 = "SES-TEST-SESSION-001"
    sess_resp = await test_client.post(
        "/api/v1/ai/interpret",
        headers={"Authorization": f"Bearer {token}"},
        json={"command": "Create a task card Login API", "conversation_id": session_id_1},
    )
    assert sess_resp.status_code == 200
    assert sess_resp.json()["conversation_id"] == session_id_1

    # Verify session listed in GET /api/v1/ai/sessions
    sessions_list_resp = await test_client.get(
        "/api/v1/ai/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert sessions_list_resp.status_code == 200
    sess_list_data = sessions_list_resp.json()
    assert sess_list_data["total"] >= 1
    found_session = any(s["id"] == session_id_1 for s in sess_list_data["sessions"])
    assert found_session is True

    # Verify history of session 1
    hist_resp = await test_client.get(
        f"/api/v1/ai/sessions/{session_id_1}/history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert hist_resp.status_code == 200
    hist_data = hist_resp.json()
    assert len(hist_data["messages"]) >= 2  # user + assistant

    # Delete session
    del_resp = await test_client.delete(
        f"/api/v1/ai/sessions/{session_id_1}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "SUCCESS"


