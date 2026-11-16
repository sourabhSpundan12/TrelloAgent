import pytest
from httpx import ASGITransport, AsyncClient
from app.database.mongodb import MongoDBManager
from app.integrations.mcp.client_manager import MCPClientManager
from app.mcp_server import create_mcp_streamable_app
from app.tool_executor.interfaces import ExecutionContext
from app.tool_executor.service import ToolExecutorService


async def get_tokens(test_client: AsyncClient):
    await test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "mcp_admin@example.com",
            "password": "Password123!",
            "full_name": "MCP Admin",
            "role": "ADMIN",
        },
    )
    admin_login = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "mcp_admin@example.com", "password": "Password123!"},
    )
    admin_token = admin_login.json()["access_token"]

    await test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "mcp_emp@example.com",
            "password": "Password123!",
            "full_name": "MCP Employee",
            "role": "EMPLOYEE",
        },
    )
    emp_login = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "mcp_emp@example.com", "password": "Password123!"},
    )
    emp_token = emp_login.json()["access_token"]

    return admin_token, emp_token


@pytest.mark.asyncio
async def test_mcp_server_registration_and_ssrf(test_client: AsyncClient):
    admin_token, emp_token = await get_tokens(test_client)

    # 1. SSRF violation: Attempting to register localhost without allow_internal
    bad_payload = {
        "server_id": "bad-internal-server",
        "name": "Bad Server",
        "transport_type": "streamable_http",
        "url": "http://127.0.0.1:8000/mcp",
        "allow_internal": False,
    }
    resp = await test_client.post(
        "/api/v1/mcp/servers",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=bad_payload,
    )
    assert resp.status_code == 400
    assert resp.json().get("error", {}).get("code") == "MCP_SSRF_VIOLATION"

    # 2. Authorization check: Non-admin cannot register MCP server
    resp = await test_client.post(
        "/api/v1/mcp/servers",
        headers={"Authorization": f"Bearer {emp_token}"},
        json={**bad_payload, "allow_internal": True},
    )
    assert resp.status_code == 403

    # 3. Successful registration with allow_internal=True
    good_payload = {
        "server_id": "test-remote-mcp",
        "name": "Test Remote MCP Server",
        "description": "Integration test server",
        "transport_type": "streamable_http",
        "url": "http://localhost:8000/mcp",
        "allow_internal": True,
    }
    resp = await test_client.post(
        "/api/v1/mcp/servers",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=good_payload,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["server_id"] == "test-remote-mcp"
    assert data["status"] == "DISCONNECTED"

    # 4. List servers
    list_resp = await test_client.get(
        "/api/v1/mcp/servers",
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert list_resp.status_code == 200
    servers = list_resp.json()["servers"]
    assert any(s["server_id"] == "test-remote-mcp" for s in servers)


@pytest.mark.asyncio
async def test_mcp_server_connect_discover_and_execute(test_client: AsyncClient):
    admin_token, _ = await get_tokens(test_client)
    db = MongoDBManager.get_db()

    subapp = create_mcp_streamable_app(streamable_http_path="/mcp")
    async with subapp.router.lifespan_context(subapp):
        async with AsyncClient(transport=ASGITransport(app=subapp), base_url="http://test") as mcp_http_client:
            client_mgr = MCPClientManager(db)
            client_mgr.register_custom_http_client("agentic-core-mcp", mcp_http_client)

            server_payload = {
                "server_id": "agentic-core-mcp",
                "name": "Agentic Core MCP Server",
                "description": "Safe read-only capabilities",
                "transport_type": "streamable_http",
                "url": "http://test/mcp",
                "allow_internal": True,
            }

            # Register server in DB via API
            reg_resp = await test_client.post(
                "/api/v1/mcp/servers",
                headers={"Authorization": f"Bearer {admin_token}"},
                json=server_payload,
            )
            assert reg_resp.status_code == 201

            # Connect to MCP server
            conn_result = await client_mgr.connect_server("agentic-core-mcp")
            assert conn_result["status"] == "CONNECTED"
            assert conn_result["latency_ms"] >= 0

            # Discover tools over official protocol
            discovery_result = await client_mgr.discover_tools("agentic-core-mcp")
            assert discovery_result.tools_discovered >= 3
            tool_names = [t["remote_tool_name"] for t in discovery_result.tools]
            assert "mcp_get_board_summary" in tool_names
            assert "mcp_search_tasks" in tool_names
            assert "mcp_get_system_status" in tool_names

            # Check tools listing endpoint
            tools_resp = await test_client.get(
                "/api/v1/mcp/servers/agentic-core-mcp/tools",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert tools_resp.status_code == 200
            registered_tools = tools_resp.json()
            assert len(registered_tools) >= 3

            # Execute discovered MCP tool via ToolExecutorService
            executor_service = ToolExecutorService(db)
            executor_service.client_manager.register_custom_http_client("agentic-core-mcp", mcp_http_client)

            exec_result = await executor_service.execute(
                tool_id="mcp.agentic-core-mcp.mcp_get_board_summary",
                parameters={"board_name": "Sprint 2026 Test"},
                context=ExecutionContext(user_id="test_admin", user_role="ADMIN", confirmed=True),
            )
            assert exec_result.status == "SUCCESS"
            assert exec_result.result["board_name"] == "Sprint 2026 Test"
            assert "lists" in exec_result.result

            # Deregister server and ensure associated tools are purged
            del_resp = await test_client.delete(
                "/api/v1/mcp/servers/agentic-core-mcp",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert del_resp.status_code == 200

            # Confirm server tools endpoint now returns 404
            tools_after = await test_client.get(
                "/api/v1/mcp/servers/agentic-core-mcp/tools",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert tools_after.status_code == 404

            # Confirm tools were completely purged from MongoDB
            remaining_tools = await db["tools"].count_documents({"source_id": "agentic-core-mcp"})
            assert remaining_tools == 0
