from fastapi import APIRouter, Depends, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.dependencies import get_current_user
from app.database.mongodb import get_database
from app.schemas.user import UserResponse
from app.tool_discovery.schemas import ToolDiscoveryRequest, ToolDiscoveryResponse
from app.tool_discovery.service import ToolDiscoveryService

router = APIRouter()


def get_tool_discovery_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> ToolDiscoveryService:
    return ToolDiscoveryService(db)


@router.post(
    "/discover",
    response_model=ToolDiscoveryResponse,
    status_code=status.HTTP_200_OK,
    summary="Discover relevant tools dynamically",
    description="Identifies and ranks relevant registered tools using hybrid keyword, semantic, and permission discovery.",
)
async def discover_tools(
    payload: ToolDiscoveryRequest,
    current_user: UserResponse = Depends(get_current_user),
    service: ToolDiscoveryService = Depends(get_tool_discovery_service),
) -> ToolDiscoveryResponse:
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    return await service.handle_discovery_request(payload, user_role=user_role_str)

