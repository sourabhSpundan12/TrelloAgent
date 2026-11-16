import pytest
from httpx import ASGITransport, AsyncClient
from app.database.mongodb import MongoDBManager
from app.integrations.gemini.service import GeminiService
from app.integrations.mcp.client_manager import MCPClientManager
from app.mcp_server import create_mcp_streamable_app, set_trello_client
from app.tool_discovery.service import ToolDiscoveryService
from app.tool_executor.interfaces import ExecutionContext
from app.tool_executor.service import ToolExecutorService
from tests.unit.test_trello_client import create_mock_trello_client


@pytest.fixture(autouse=True)
def setup_mock_trello():
    mock_client = create_mock_trello_client()
    set_trello_client(mock_client)
    yield
    set_trello_client(None)


@pytest.mark.asyncio
async def test_trello_mcp_discovery_execution_and_agent(test_client: AsyncClient):
    db = MongoDBManager.get_db()

    # 1. Setup in-task MCP server over Streamable HTTP
    subapp = create_mcp_streamable_app(streamable_http_path="/mcp")
    async with subapp.router.lifespan_context(subapp):
        async with AsyncClient(transport=ASGITransport(app=subapp), base_url="http://test") as mcp_http_client:
            client_mgr = MCPClientManager(db)
            client_mgr.register_custom_http_client("trello-mcp", mcp_http_client)

            # Register Trello MCP Server in DB
            await client_mgr.server_repo.create({
                "server_id": "trello-mcp",
                "name": "Live Trello MCP Service",
                "description": "Exposes Trello boards, lists, and card operations via MCP",
                "transport_type": "streamable_http",
                "url": "http://test/mcp",
                "allow_internal": True,
                "timeout_seconds": 10.0,
            })

            # Connect to server
            conn_res = await client_mgr.connect_server("trello-mcp")
            assert conn_res["status"] == "CONNECTED"

            # 2. Discover MCP tools into Tool Registry
            disc_res = await client_mgr.discover_tools("trello-mcp")
            assert disc_res.tools_discovered >= 12
            discovered_remote_names = [t["remote_tool_name"] for t in disc_res.tools]
            expected_trello_tools = [
                "trello_list_boards",
                "trello_get_board",
                "trello_list_lists",
                "trello_list_cards",
                "trello_get_card",
                "trello_create_card",
                "trello_update_card",
                "trello_move_card",
                "trello_archive_card",
            ]
            for tool_name in expected_trello_tools:
                assert tool_name in discovered_remote_names

            # 3. Tool Executor: invoke Trello MCP tools
            executor = ToolExecutorService(db)
            executor.client_manager.register_custom_http_client("trello-mcp", mcp_http_client)

            # A. Execute trello_list_boards
            res_boards = await executor.execute(
                tool_id="mcp.trello-mcp.trello_list_boards",
                parameters={},
                context=ExecutionContext(user_id="test_user", user_role="ADMIN", confirmed=True),
            )
            assert res_boards.status == "SUCCESS"
            assert res_boards.result["total"] == 2
            assert res_boards.is_mutation is False

            # B. Execute trello_create_card
            res_create = await executor.execute(
                tool_id="mcp.trello-mcp.trello_create_card",
                parameters={"name": "End-to-End Task Card", "desc": "Phase 5 verification"},
                context=ExecutionContext(user_id="test_user", user_role="ADMIN", confirmed=True),
            )
            assert res_create.status == "SUCCESS"
            assert res_create.result["card"]["name"] == "End-to-End Task Card"
            assert res_create.is_mutation is True

            # C. Execute trello_move_card
            res_move = await executor.execute(
                tool_id="mcp.trello-mcp.trello_move_card",
                parameters={"card_id": "c1", "list_id": "l_done"},
                context=ExecutionContext(user_id="test_user", user_role="ADMIN", confirmed=True),
            )
            assert res_move.status == "SUCCESS"
            assert res_move.result["card"]["idList"] == "l_done"
            assert res_move.is_mutation is True

            # D. Execute trello_archive_card
            res_archive = await executor.execute(
                tool_id="mcp.trello-mcp.trello_archive_card",
                parameters={"card_id": "c1"},
                context=ExecutionContext(user_id="test_user", user_role="ADMIN", confirmed=True),
            )
            assert res_archive.status == "SUCCESS"
            assert res_archive.result["card"]["closed"] is True

            # 4. AI Agent Discovery and Intent Interpretation
            discovery_service = ToolDiscoveryService(db)
            gemini_service = GeminiService()

            # Test A: "Show my Trello boards"
            discovered_boards = await discovery_service.discover_tools("Show my Trello boards")
            assert len(discovered_boards) > 0
            intent_boards = await gemini_service.interpret_command("Show my Trello boards", discovered_boards)
            assert intent_boards.intent == "list_boards"
            assert intent_boards.suggested_tool_id == "mcp.trello-mcp.trello_list_boards"

            # Test B: "Create a task named Implement User Authentication"
            discovered_create = await discovery_service.discover_tools("Create a task named Implement User Authentication")
            assert len(discovered_create) > 0
            intent_create = await gemini_service.interpret_command("Create a task named Implement User Authentication", discovered_create)
            assert intent_create.intent == "create_card"
            assert intent_create.parameters["name"] == "Implement User Authentication"
            assert intent_create.suggested_tool_id == "mcp.trello-mcp.trello_create_card"

            # Test C: "Move a task from To Do to Doing"
            discovered_move = await discovery_service.discover_tools("Move task to Doing")
            assert len(discovered_move) > 0
            intent_move = await gemini_service.interpret_command("Move a task from To Do to Doing", discovered_move)
            assert intent_move.intent == "move_card"
            assert intent_move.suggested_tool_id == "mcp.trello-mcp.trello_move_card"

            # Test D: "Show cards in the To Do list"
            discovered_cards = await discovery_service.discover_tools("Show cards in the To Do list")
            assert len(discovered_cards) > 0
            intent_cards = await gemini_service.interpret_command("Show cards in the To Do list", discovered_cards)
            assert intent_cards.intent == "list_cards"
            assert intent_cards.suggested_tool_id == "mcp.trello-mcp.trello_list_cards"

            # Cleanup
            await client_mgr.remove_server_and_tools("trello-mcp")

