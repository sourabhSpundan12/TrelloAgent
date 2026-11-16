from datetime import datetime, timezone
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_team_workload_api(test_client: AsyncClient, mock_db):
    # 1. Register & login test user
    reg_res = await test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "team_user@example.com",
            "password": "Password123!",
            "full_name": "Sourabh Mishra",
            "role": "ADMIN",
            "department": "Engineering",
        },
    )
    assert reg_res.status_code == 201

    login_res = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "team_user@example.com", "password": "Password123!"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Mock trello tools responses
    mock_members = [
        {"id": "mem_sourabh_01", "fullName": "Sourabh Mishra", "username": "sourabhmishra"},
    ]
    mock_cards = [
        {
            "id": "card_jwt_01",
            "name": "JWT authentication",
            "desc": "Implement JWT endpoints",
            "idList": "list_doing_01",
            "idBoard": "board_01",
            "closed": False,
            "url": "https://trello.com/c/test1",
            "due": "2026-11-26T17:00:00.000Z",
            "idMembers": ["mem_sourabh_01"],
        },
        {
            "id": "card_onboard_02",
            "name": "Complete client OnBoard",
            "desc": "Onboarding tasks for client",
            "idList": "list_todo_01",
            "idBoard": "board_01",
            "closed": False,
            "url": "https://trello.com/c/test2",
            "due": "2026-11-20T17:00:00.000Z",
            "idMembers": ["mem_sourabh_01"],
        },
    ]
    mock_lists = [
        {"id": "list_todo_01", "name": "To Do"},
        {"id": "list_doing_01", "name": "Doing"},
        {"id": "list_done_01", "name": "Done"},
    ]

    with patch("app.mcp_server.trello_tools.trello_list_board_members", new_callable=AsyncMock) as m_members, \
         patch("app.mcp_server.trello_tools.trello_list_cards", new_callable=AsyncMock) as m_cards, \
         patch("app.mcp_server.trello_tools.trello_list_lists", new_callable=AsyncMock) as m_lists:
        m_members.return_value = {"status": "SUCCESS", "members": mock_members, "total": 1}
        m_cards.return_value = {"status": "SUCCESS", "cards": mock_cards, "total": 2}
        m_lists.return_value = {"status": "SUCCESS", "lists": mock_lists, "total": 3}

        # 3. Call GET /api/v1/tasks/team
        resp = await test_client.get("/api/v1/tasks/team", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        assert data["status"] == "SUCCESS"
        assert data["total_members"] >= 1

        sourabh = next((m for m in data["members"] if "sourabh" in m["name"].lower()), None)
        assert sourabh is not None
        assert sourabh["assignedTasksCount"] == 2
        assert len(sourabh["tasks"]) == 2
        assert any(t["title"] == "JWT authentication" for t in sourabh["tasks"])
        assert any(t["title"] == "Complete client OnBoard" for t in sourabh["tasks"])

