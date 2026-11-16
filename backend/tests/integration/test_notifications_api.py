from datetime import datetime, timezone
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_notifications_api_full_lifecycle(test_client: AsyncClient, mock_db):
    # 1. Register & login test user
    reg_res = await test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "notif_user@example.com",
            "password": "Password123!",
            "full_name": "Notif User",
            "role": "EMPLOYEE",
        },
    )
    assert reg_res.status_code == 201

    login_res = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "notif_user@example.com", "password": "Password123!"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Get notifications when empty
    empty_resp = await test_client.get("/api/v1/notifications", headers=headers)
    assert empty_resp.status_code == 200
    empty_data = empty_resp.json()
    assert empty_data["status"] == "SUCCESS"
    assert empty_data["unread_count"] == 0
    assert len(empty_data["notifications"]) == 0

    # 3. Insert real pending action
    now = datetime.now(timezone.utc)
    await mock_db["pending_actions"].insert_one({
        "action_id": "ACT-NOTIF-01",
        "action_type": "CREATE_CARD",
        "tool_id": "trello_create_card",
        "status": "PENDING",
        "command": "Create login API card",
        "draft": {
            "title": "Login API",
            "description": "Implement authentication endpoints",
            "priority": "HIGH",
            "due_date": "2026-11-20",
        },
        "created_at": now,
        "updated_at": now,
    })

    # 4. Fetch notifications again
    resp = await test_client.get("/api/v1/notifications", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["unread_count"] == 1
    assert len(data["notifications"]) == 1

    notif = data["notifications"][0]
    assert notif["type"] == "APPROVAL_REQUIRED"
    assert notif["title"] == "Pending Approval Required"
    assert "Login API" in notif["message"]
    assert notif["is_read"] is False
    assert notif["action_id"] == "ACT-NOTIF-01"

    # 5. Mark single notification as read
    mark_resp = await test_client.post(
        "/api/v1/notifications/mark-read",
        headers=headers,
        json={"notification_id": notif["id"]},
    )
    assert mark_resp.status_code == 200

    resp_after = await test_client.get("/api/v1/notifications", headers=headers)
    assert resp_after.status_code == 200
    data_after = resp_after.json()
    assert data_after["unread_count"] == 0
    assert data_after["notifications"][0]["is_read"] is True

    # 6. Insert executed action
    await mock_db["pending_actions"].insert_one({
        "action_id": "ACT-NOTIF-02",
        "action_type": "UPDATE_CARD",
        "tool_id": "trello_update_card",
        "status": "EXECUTED",
        "command": "Assign member to card",
        "draft": {
            "title": "JWT authentication",
            "description": "Assign sourabh mishra",
        },
        "execution_result": {
            "status": "SUCCESS",
            "result": {
                "card": {
                    "id": "card123",
                    "name": "JWT authentication",
                    "url": "https://trello.com/c/test1234",
                }
            }
        },
        "created_at": now,
        "updated_at": now,
    })

    resp_exec = await test_client.get("/api/v1/notifications", headers=headers)
    assert resp_exec.status_code == 200
    data_exec = resp_exec.json()
    assert data_exec["unread_count"] == 1
    assert len(data_exec["notifications"]) == 2

    exec_notif = next(n for n in data_exec["notifications"] if n["action_id"] == "ACT-NOTIF-02")
    assert exec_notif["type"] == "ACTION_EXECUTED"
    assert exec_notif["title"] == "Action Executed in Trello"
    assert exec_notif["card_url"] == "https://trello.com/c/test1234"

    # 7. Mark all as read
    mark_all_resp = await test_client.post(
        "/api/v1/notifications/mark-read",
        headers=headers,
        json={"mark_all": True},
    )
    assert mark_all_resp.status_code == 200

    resp_all_read = await test_client.get("/api/v1/notifications", headers=headers)
    assert resp_all_read.status_code == 200
    assert resp_all_read.json()["unread_count"] == 0

