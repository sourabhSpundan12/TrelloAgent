import pytest
from httpx import AsyncClient


async def get_auth_tokens(test_client: AsyncClient):
    # Register Admin
    await test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "tool_admin@example.com",
            "password": "Password123!",
            "full_name": "Tool Admin",
            "role": "ADMIN",
        },
    )
    admin_login = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "tool_admin@example.com", "password": "Password123!"},
    )
    admin_token = admin_login.json()["access_token"]

    # Register Employee
    await test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "tool_emp@example.com",
            "password": "Password123!",
            "full_name": "Tool Employee",
            "role": "EMPLOYEE",
        },
    )
    emp_login = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "tool_emp@example.com", "password": "Password123!"},
    )
    emp_token = emp_login.json()["access_token"]

    return admin_token, emp_token


@pytest.mark.asyncio
async def test_tool_registry_and_discovery_endpoints(test_client: AsyncClient):
    admin_token, emp_token = await get_auth_tokens(test_client)

    # 1. Register a new tool as ADMIN (201 Created)
    new_tool = {
        "tool_id": "api_custom_tool",
        "name": "API Custom Tool",
        "description": "Tool registered via REST API endpoint.",
        "category": "project_management",
        "keywords": ["project", "api", "custom"],
        "synonyms": ["run project tool"],
        "capabilities": ["custom_ops"],
        "input_schema": {
            "type": "object",
            "properties": {"task_name": {"type": "string"}},
            "required": ["task_name"],
        },
        "permissions": ["EMPLOYEE", "ADMIN"],
        "executor_type": "mock",
        "executor_key": "mock.echo",
        "version": "1.0.0",
        "enabled": True,
        "approval_required": False,
    }

    reg_resp = await test_client.post(
        "/api/v1/tools/register",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=new_tool,
    )
    assert reg_resp.status_code == 201
    assert reg_resp.json()["tool_id"] == "api_custom_tool"

    # 2. RBAC: Attempting to register as EMPLOYEE (403 Forbidden)
    emp_reg_resp = await test_client.post(
        "/api/v1/tools/register",
        headers={"Authorization": f"Bearer {emp_token}"},
        json=new_tool,
    )
    assert emp_reg_resp.status_code == 403

    # 3. GET /api/v1/tools
    list_resp = await test_client.get(
        "/api/v1/tools",
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1
    assert any(t["tool_id"] == "api_custom_tool" for t in list_data["tools"])

    # 4. GET /api/v1/tools/{tool_id}
    get_resp = await test_client.get(
        "/api/v1/tools/api_custom_tool",
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "API Custom Tool"

    # 5. PATCH /api/v1/tools/{tool_id} as ADMIN
    patch_resp = await test_client.patch(
        "/api/v1/tools/api_custom_tool",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"description": "Updated tool description via PATCH"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["description"] == "Updated tool description via PATCH"

    # 6. POST /api/v1/tools/{tool_id}/disable
    disable_resp = await test_client.post(
        "/api/v1/tools/api_custom_tool/disable",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert disable_resp.status_code == 200
    assert disable_resp.json()["enabled"] is False

    # 7. POST /api/v1/tools/discover (Ensure disabled tool is NOT returned)
    discover_resp = await test_client.post(
        "/api/v1/tools/discover",
        headers={"Authorization": f"Bearer {emp_token}"},
        json={"query": "run project tool custom", "limit": 5},
    )
    assert discover_resp.status_code == 200
    disc_data = discover_resp.json()
    assert not any(t["tool"]["tool_id"] == "api_custom_tool" for t in disc_data["tools"])

    # 8. POST /api/v1/tools/{tool_id}/enable
    enable_resp = await test_client.post(
        "/api/v1/tools/api_custom_tool/enable",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert enable_resp.status_code == 200
    assert enable_resp.json()["enabled"] is True

    # 9. POST /api/v1/tools/discover after re-enabling
    discover_resp2 = await test_client.post(
        "/api/v1/tools/discover",
        headers={"Authorization": f"Bearer {emp_token}"},
        json={"query": "run project tool custom", "limit": 5},
    )
    assert discover_resp2.status_code == 200
    assert any(t["tool"]["tool_id"] == "api_custom_tool" for t in discover_resp2.json()["tools"])

