from fastapi import APIRouter, Depends, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.approvals.schemas import (
    ApprovalCancelResponse,
    ApprovalConfirmResponse,
    ApprovalEditRequest,
    ApprovalPreviewResponse,
)
from app.approvals.service import ApprovalService
from app.chat.repository import ChatRepository
from app.core.dependencies import get_current_user
from app.database.mongodb import get_database
from app.schemas.user import UserResponse

router = APIRouter()


def get_approval_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> ApprovalService:
    return ApprovalService(db)


def get_chat_repo(db: AsyncIOMotorDatabase = Depends(get_database)) -> ChatRepository:
    return ChatRepository(db)


@router.get(
    "/{action_id}",
    response_model=ApprovalPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Get pending action draft preview",
    description="Fetches a structured preview of a pending action by its action_id. Verifies user ownership and TTL expiration.",
)
async def get_action_preview(
    action_id: str,
    current_user: UserResponse = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service),
) -> ApprovalPreviewResponse:
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    return await service.get_action(
        action_id=action_id,
        user_id=current_user.id,
        user_role=user_role_str,
    )


@router.post(
    "/{action_id}/confirm",
    response_model=ApprovalConfirmResponse,
    status_code=status.HTTP_200_OK,
    summary="Confirm and execute pending action",
    description="Explicitly approves and executes a pending action draft via MCP / tool executor. Enforces atomic locking to prevent duplicate executions.",
)
async def confirm_action(
    action_id: str,
    current_user: UserResponse = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service),
    chat_repo: ChatRepository = Depends(get_chat_repo),
) -> ApprovalConfirmResponse:
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    res = await service.confirm_action(
        action_id=action_id,
        user_id=current_user.id,
        user_role=user_role_str,
    )
    # Sync with persistent chat message in Atlas
    await chat_repo.update_action_status_in_chat(
        action_id=action_id,
        new_status="EXECUTED",
        card_url=res.card_url,
        card_id=res.card_id,
        execution_result=res.execution_result,
    )
    return res


@router.patch(
    "/{action_id}",
    response_model=ApprovalPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Edit pending action draft parameters",
    description="Modifies fields on a pending task draft (title, description, list, priority, due date) and recomputes the payload hash.",
)
async def edit_action(
    action_id: str,
    payload: ApprovalEditRequest,
    current_user: UserResponse = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service),
    chat_repo: ChatRepository = Depends(get_chat_repo),
) -> ApprovalPreviewResponse:
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    res = await service.edit_action(
        action_id=action_id,
        user_id=current_user.id,
        user_role=user_role_str,
        edit_data=payload,
    )
    # Sync with persistent chat message in Atlas
    await chat_repo.update_action_status_in_chat(
        action_id=action_id,
        new_status="PENDING",
        updated_draft=res.draft.model_dump() if hasattr(res.draft, "model_dump") else res.draft,
    )
    return res


@router.post(
    "/{action_id}/cancel",
    response_model=ApprovalCancelResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel and reject pending action draft",
    description="Marks a pending action draft as REJECTED, discarding it and preventing any future execution.",
)
async def cancel_action(
    action_id: str,
    current_user: UserResponse = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service),
    chat_repo: ChatRepository = Depends(get_chat_repo),
) -> ApprovalCancelResponse:
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    res = await service.cancel_action(
        action_id=action_id,
        user_id=current_user.id,
        user_role=user_role_str,
    )
    # Sync with persistent chat message in Atlas
    await chat_repo.update_action_status_in_chat(
        action_id=action_id,
        new_status="REJECTED",
    )
    return res

