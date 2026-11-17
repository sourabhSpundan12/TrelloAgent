import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_boards_api_lifecycle(test_client: AsyncClient, mock_db):
    # 1. Register & login test user
    reg_res = await test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "board_tester@example.com",
            "password": "Password123!",
            "full_name": "Board Tester",
            "role": "ADMIN",
        },
    )
    assert reg_res.status_code == 201

    login_res = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "board_tester@example.com", "password": "Password123!"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. List initial boards (auto-seeded default board)
    list_res = await test_client.get("/api/v1/boards", headers=headers)
    assert list_res.status_code == 200
    data = list_res.json()
    assert data["status"] == "SUCCESS"
    assert data["total"] >= 1
    assert data["active_board_id"] != ""
    initial_active_id = data["active_board_id"]

    # 3. Add a new board
    create_res = await test_client.post(
        "/api/v1/boards",
        headers=headers,
        json={
            "board_id": "7bf6799694a7f5e7a002160c",
            "name": "Mobile Engineering Sprint",
            "desc": "Sprint board for iOS and Android dev",
        },
    )
    assert create_res.status_code == 201
    created_board = create_res.json()
    assert created_board["board_id"] == "7bf6799694a7f5e7a002160c"
    assert created_board["name"] == "Mobile Engineering Sprint"
    assert created_board["is_active"] is False

    # 4. Activate the newly created board
    activate_res = await test_client.post(
        f"/api/v1/boards/{created_board['board_id']}/activate",
        headers=headers,
    )
    assert activate_res.status_code == 200
    activated_board = activate_res.json()
    assert activated_board["board_id"] == created_board["board_id"]
    assert activated_board["is_active"] is True

    # 5. Verify GET /api/v1/boards/active returns the new board
    active_res = await test_client.get("/api/v1/boards/active", headers=headers)
    assert active_res.status_code == 200
    assert active_res.json()["board_id"] == created_board["board_id"]

    # 6. Verify chat sessions isolation: listing sessions for new board returns 0 initially
    sessions_res = await test_client.get(
        f"/api/v1/ai/sessions?board_id={created_board['board_id']}",
        headers=headers,
    )
    assert sessions_res.status_code == 200
    assert sessions_res.json()["total"] == 0

    # 7. Test deactivating board
    deact_res = await test_client.post(
        f"/api/v1/boards/{created_board['board_id']}/deactivate",
        headers=headers,
    )
    assert deact_res.status_code == 200
    assert deact_res.json()["is_active"] is False

    # 8. Test toggling board status
    toggle_res = await test_client.post(
        f"/api/v1/boards/{created_board['board_id']}/toggle",
        headers=headers,
    )
    assert toggle_res.status_code == 200
    assert toggle_res.json()["is_active"] is True

    # 9. Test re-adding an existing board (upsert behavior without 400 error)
    readd_res = await test_client.post(
        "/api/v1/boards",
        headers=headers,
        json={
            "board_id": created_board["board_id"],
            "name": "Updated Board Name",
        },
    )
    assert readd_res.status_code in [200, 201]
    assert readd_res.json()["name"] == "Updated Board Name"

    # 10. Delete the newly created board (after switching active back to initial)
    await test_client.post(f"/api/v1/boards/{initial_active_id}/activate", headers=headers)
    del_res = await test_client.delete(f"/api/v1/boards/{created_board['board_id']}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "SUCCESS"

