from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.dependencies import get_current_user, require_roles
from app.core.exceptions import AppException
from app.database.mongodb import get_database
from app.integrations.mcp.client_manager import MCPClientManager
from app.integrations.mcp.exceptions import (
    MCPDiscoveryError,
    MCPServerConnectionError,
    MCPServerNotFoundError,
    MCPSSRFError,
)
from app.integrations.mcp.repository import MCPServerRepository
from app.integrations.mcp.schemas import (
    MCPDiscoveredToolsResponse,
    MCPServerListResponse,
    MCPServerRegisterRequest,
    MCPServerResponse,
)
from app.integrations.mcp.transport import validate_url_ssrf
from app.models.user import UserRole
from app.schemas.user import UserResponse
from app.tool_registry.schemas import ToolResponse

router = APIRouter()


def get_client_manager(db: AsyncIOMotorDatabase = Depends(get_database)) -> MCPClientManager:
    return MCPClientManager(db)


def get_server_repo(db: AsyncIOMotorDatabase = Depends(get_database)) -> MCPServerRepository:
    return MCPServerRepository(db)


@router.get(
    "/servers",
    response_model=MCPServerListResponse,
    status_code=status.HTTP_200_OK,
    summary="List registered MCP servers",
    description="Retrieve all configured MCP servers with status and metadata.",
)
async def list_servers(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    enabled: Optional[bool] = Query(None),
    _: UserResponse = Depends(get_current_user),
    repo: MCPServerRepository = Depends(get_server_repo),
) -> MCPServerListResponse:
    servers, total = await repo.list_servers(skip=skip, limit=limit, enabled=enabled)
    return MCPServerListResponse(
        servers=[MCPServerResponse(**s) for s in servers],
        total=total,
    )


@router.post(
    "/servers",
    response_model=MCPServerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new MCP server (Admin only)",
    description="Register an external or local MCP server into the system with SSRF validation.",
)
async def register_server(
    payload: MCPServerRegisterRequest,
    _: UserResponse = Depends(require_roles([UserRole.ADMIN])),
    repo: MCPServerRepository = Depends(get_server_repo),
) -> MCPServerResponse:
    existing = await repo.get_by_server_id(payload.server_id)
    if existing:
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            message=f"MCP server with ID '{payload.server_id}' is already registered.",
            error_code="MCP_SERVER_EXISTS",
        )

    # Validate SSRF for HTTP / SSE URLs
    if payload.transport_type in ("streamable_http", "sse") and payload.url:
        try:
            validate_url_ssrf(payload.url, allow_internal=payload.allow_internal)
        except MCPSSRFError as err:
            raise AppException(
                status_code=status.HTTP_400_BAD_REQUEST,
                message=str(err),
                error_code="MCP_SSRF_VIOLATION",
            )

    server_doc = payload.model_dump()
    created = await repo.create(server_doc)
    return MCPServerResponse(**created)


@router.get(
    "/servers/{server_id}",
    response_model=MCPServerResponse,
    status_code=status.HTTP_200_OK,
    summary="Get MCP server details",
    description="Retrieve status, transport configuration, and tool metrics for a registered MCP server.",
)
async def get_server(
    server_id: str,
    _: UserResponse = Depends(get_current_user),
    repo: MCPServerRepository = Depends(get_server_repo),
) -> MCPServerResponse:
    server = await repo.get_by_server_id(server_id)
    if not server:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"MCP server '{server_id}' was not found.",
            error_code="MCP_SERVER_NOT_FOUND",
        )
    return MCPServerResponse(**server)


@router.post(
    "/servers/{server_id}/connect",
    status_code=status.HTTP_200_OK,
    summary="Test and establish connection to MCP server (Admin only)",
    description="Initializes session and pings remote MCP server, updating status.",
)
async def connect_server(
    server_id: str,
    _: UserResponse = Depends(require_roles([UserRole.ADMIN])),
    client_mgr: MCPClientManager = Depends(get_client_manager),
) -> Dict[str, Any]:
    try:
        return await client_mgr.connect_server(server_id)
    except MCPServerNotFoundError as err:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message=str(err),
            error_code="MCP_SERVER_NOT_FOUND",
        )
    except MCPServerConnectionError as err:
        raise AppException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            message=str(err),
            error_code="MCP_CONNECTION_FAILED",
        )
    except MCPSSRFError as err:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=str(err),
            error_code="MCP_SSRF_VIOLATION",
        )


@router.post(
    "/servers/{server_id}/disconnect",
    status_code=status.HTTP_200_OK,
    summary="Disconnect an MCP server (Admin only)",
    description="Marks the MCP server as DISCONNECTED.",
)
async def disconnect_server(
    server_id: str,
    _: UserResponse = Depends(require_roles([UserRole.ADMIN])),
    client_mgr: MCPClientManager = Depends(get_client_manager),
) -> Dict[str, Any]:
    try:
        return await client_mgr.disconnect_server(server_id)
    except MCPServerNotFoundError as err:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message=str(err),
            error_code="MCP_SERVER_NOT_FOUND",
        )


@router.post(
    "/servers/{server_id}/discover",
    response_model=MCPDiscoveredToolsResponse,
    status_code=status.HTTP_200_OK,
    summary="Discover and synchronize tools from MCP server (Admin only)",
    description="Fetches exposed tools via tools/list, adapts them into ToolModel, and persists them into Tool Registry.",
)
async def discover_server_tools(
    server_id: str,
    _: UserResponse = Depends(require_roles([UserRole.ADMIN])),
    client_mgr: MCPClientManager = Depends(get_client_manager),
) -> MCPDiscoveredToolsResponse:
    try:
        return await client_mgr.discover_tools(server_id)
    except MCPServerNotFoundError as err:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message=str(err),
            error_code="MCP_SERVER_NOT_FOUND",
        )
    except (MCPDiscoveryError, MCPServerConnectionError) as err:
        raise AppException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            message=str(err),
            error_code="MCP_DISCOVERY_FAILED",
        )


@router.get(
    "/servers/{server_id}/tools",
    response_model=List[ToolResponse],
    status_code=status.HTTP_200_OK,
    summary="List tools registered from this MCP server",
    description="Retrieve all tools in the registry associated with this server_id.",
)
async def get_server_tools(
    server_id: str,
    _: UserResponse = Depends(get_current_user),
    client_mgr: MCPClientManager = Depends(get_client_manager),
) -> List[ToolResponse]:
    try:
        await client_mgr.get_server_or_fail(server_id)
    except MCPServerNotFoundError as err:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message=str(err),
            error_code="MCP_SERVER_NOT_FOUND",
        )
    cursor = client_mgr.tool_repo.collection.find({"source_type": "MCP", "source_id": server_id})
    tools = []
    async for doc in cursor:
        doc.pop("_id", None)
        tools.append(ToolResponse(**doc))
    return tools


@router.delete(
    "/servers/{server_id}",
    status_code=status.HTTP_200_OK,
    summary="Deregister MCP server and purge associated tools (Admin only)",
    description="Removes the server registration and cleans up all synchronized tools from the Tool Registry.",
)
async def delete_server(
    server_id: str,
    _: UserResponse = Depends(require_roles([UserRole.ADMIN])),
    client_mgr: MCPClientManager = Depends(get_client_manager),
) -> Dict[str, Any]:
    deleted = await client_mgr.remove_server_and_tools(server_id)
    if not deleted:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"MCP server '{server_id}' not found.",
            error_code="MCP_SERVER_NOT_FOUND",
        )
    return {
        "status": "DELETED",
        "server_id": server_id,
        "message": f"MCP server '{server_id}' and all associated tools were purged successfully.",
    }

