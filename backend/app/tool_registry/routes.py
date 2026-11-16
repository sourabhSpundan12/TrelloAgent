from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.dependencies import get_current_user, require_roles
from app.database.mongodb import get_database
from app.models.user import UserRole
from app.schemas.user import UserResponse
from app.tool_registry.schemas import (
    ToolListResponse,
    ToolRegisterRequest,
    ToolResponse,
    ToolUpdateRequest,
)
from app.tool_registry.service import ToolRegistryService

router = APIRouter()


def get_tool_registry_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> ToolRegistryService:
    return ToolRegistryService(db)


@router.get(
    "",
    response_model=ToolListResponse,
    status_code=status.HTTP_200_OK,
    summary="List registered tools",
    description="Retrieve paginated tools with optional category and enabled status filtering.",
)
async def list_tools(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    category: Optional[str] = Query(None, description="Filter by tool category"),
    enabled: Optional[bool] = Query(None, description="Filter by enabled status"),
    _: UserResponse = Depends(get_current_user),
    service: ToolRegistryService = Depends(get_tool_registry_service),
) -> ToolListResponse:
    return await service.list_tools(page=page, page_size=page_size, category=category, enabled=enabled)


@router.post(
    "/register",
    response_model=ToolResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new tool (Admin only)",
    description="Registers a new tool in the dynamic registry. Requires ADMIN role.",
)
async def register_tool(
    payload: ToolRegisterRequest,
    _: UserResponse = Depends(require_roles([UserRole.ADMIN])),
    service: ToolRegistryService = Depends(get_tool_registry_service),
) -> ToolResponse:
    return await service.register_tool(payload)


@router.get(
    "/{tool_id}",
    response_model=ToolResponse,
    status_code=status.HTTP_200_OK,
    summary="Get tool details",
    description="Retrieve complete metadata, capabilities, and input schema for a registered tool.",
)
async def get_tool(
    tool_id: str,
    _: UserResponse = Depends(get_current_user),
    service: ToolRegistryService = Depends(get_tool_registry_service),
) -> ToolResponse:
    return await service.get_tool(tool_id)


@router.patch(
    "/{tool_id}",
    response_model=ToolResponse,
    status_code=status.HTTP_200_OK,
    summary="Update tool metadata (Admin only)",
    description="Update metadata, version, schema, or permissions for an existing tool. Requires ADMIN role.",
)
async def update_tool(
    tool_id: str,
    payload: ToolUpdateRequest,
    _: UserResponse = Depends(require_roles([UserRole.ADMIN])),
    service: ToolRegistryService = Depends(get_tool_registry_service),
) -> ToolResponse:
    return await service.update_tool(tool_id, payload)


@router.post(
    "/{tool_id}/enable",
    response_model=ToolResponse,
    status_code=status.HTTP_200_OK,
    summary="Enable a tool (Admin only)",
    description="Activates a tool, making it discoverable and executable by authorized users. Requires ADMIN role.",
)
async def enable_tool(
    tool_id: str,
    _: UserResponse = Depends(require_roles([UserRole.ADMIN])),
    service: ToolRegistryService = Depends(get_tool_registry_service),
) -> ToolResponse:
    return await service.enable_tool(tool_id)


@router.post(
    "/{tool_id}/disable",
    response_model=ToolResponse,
    status_code=status.HTTP_200_OK,
    summary="Disable a tool (Admin only)",
    description="Deactivates a tool. Disabled tools are immediately excluded from AI discovery and execution. Requires ADMIN role.",
)
async def disable_tool(
    tool_id: str,
    _: UserResponse = Depends(require_roles([UserRole.ADMIN])),
    service: ToolRegistryService = Depends(get_tool_registry_service),
) -> ToolResponse:
    return await service.disable_tool(tool_id)

