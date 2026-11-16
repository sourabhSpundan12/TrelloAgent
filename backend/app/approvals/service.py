from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import uuid
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.approvals.exceptions import (
    ApprovalAlreadyProcessedError,
    ApprovalExecutionError,
    ApprovalExpiredError,
    ApprovalNotFoundError,
    ApprovalUnauthorizedError,
)
from app.approvals.models import ApprovalStatus, PendingActionModel, TaskDraft
from app.approvals.repository import ApprovalRepository
from app.approvals.schemas import (
    ApprovalCancelResponse,
    ApprovalConfirmResponse,
    ApprovalEditRequest,
    ApprovalPreviewResponse,
    TaskDraftSchema,
)
from app.core.config import Settings
from app.core.logging import logger
from app.core.security import compute_payload_hash
from app.tool_executor.interfaces import ExecutionContext
from app.tool_executor.service import ToolExecutorService

settings = Settings()


class ApprovalService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.repository = ApprovalRepository(db)
        self.tool_executor = ToolExecutorService(db)

    @staticmethod
    def _generate_related_description(title: str, command: str) -> str:
        clean_title = title.strip()
        if clean_title.lower() in ("task", "card", "new task", "new card") and len(command.strip()) > len(clean_title):
            clean_title = command.strip()

        return (
            f"Implement and complete deliverables for '{clean_title}'. "
            f"Scope includes requirement analysis, architectural setup, functionality testing, and deployment verification."
        )

    async def create_task_draft(
        self,
        user_id: str,
        user_email: Optional[str],
        command: str,
        intent: str,
        tool_id: str,
        tool_name: str,
        category: str,
        parameters: Dict[str, Any],
        board_name: Optional[str] = None,
        board_id: Optional[str] = None,
        action_type: Optional[str] = None,
    ) -> ApprovalPreviewResponse:
        """
        Constructs a structured task draft from user command and extracted parameters,
        computes deterministic payload hash, assigns TTL expiration, and stores in MongoDB pending_actions.
        """
        action_id = f"ACT-PREV-{uuid.uuid4().hex[:8].upper()}"

        # Determine action type
        if not action_type:
            intent_lower = intent.lower()
            if "create_list" in intent_lower or "create_list" in tool_id or "add_list" in intent_lower:
                action_type = "CREATE_LIST"
            elif "create" in intent_lower or "create" in tool_id:
                action_type = "CREATE_CARD"
            elif "move" in intent_lower or "move" in tool_id:
                action_type = "MOVE_CARD"
            elif "update" in intent_lower or "update" in tool_id:
                action_type = "UPDATE_CARD"
            elif "archive" in intent_lower or "archive" in tool_id or "delete" in tool_id:
                action_type = "ARCHIVE_CARD"
            else:
                action_type = "MUTATION"

        # Resolve title / card name
        raw_name = (
            parameters.get("name")
            or parameters.get("title")
            or parameters.get("card_name")
            or parameters.get("list_name")
            or command
        )
        title = str(raw_name).strip()

        # Resolve board
        target_board_id = board_id or parameters.get("board_id") or settings.TRELLO_BOARD_ID or None
        target_board_name = board_name or "Configured Trello Board"

        # Resolve list
        list_name = (
            parameters.get("list_name")
            or parameters.get("target_status")
            or "To Do"
        )
        list_id = parameters.get("list_id")

        # Resolve description
        if action_type == "CREATE_LIST":
            description = f"Create new column/list '{title}' on the board."
        elif action_type == "MOVE_CARD":
            raw_desc = parameters.get("desc") or parameters.get("description")
            if raw_desc and "task created via agentic assistant" not in str(raw_desc).lower() and str(raw_desc).strip() != "":
                description = str(raw_desc).strip()
            else:
                description = f"Move card '{title}' to {list_name}."
        elif action_type == "UPDATE_CARD":
            raw_desc = parameters.get("desc") or parameters.get("description") or parameters.get("new_description")
            member_name = parameters.get("member_name") or parameters.get("assignee")
            if member_name:
                description = f"Assign member '{member_name}' to card '{title}'."
                if raw_desc:
                    description += f" Notes: {raw_desc}"
            elif raw_desc and "task created via agentic assistant" not in str(raw_desc).lower() and str(raw_desc).strip() != "":
                description = str(raw_desc).strip()
            else:
                description = f"Update card '{title}' on the board."
        elif action_type in ("ARCHIVE_CARD", "DELETE_CARD"):
            description = f"Permanently archive / delete card '{title}' from Trello board."
        else:
            raw_desc = parameters.get("desc") or parameters.get("description")
            if not raw_desc or "task created via agentic assistant" in str(raw_desc).lower() or str(raw_desc).strip() == "":
                description = self._generate_related_description(title, command)
            else:
                description = str(raw_desc).strip()

        # Resolve priority & due date
        priority = (parameters.get("priority") or "MEDIUM").upper()
        due_date = parameters.get("due_date") or parameters.get("due") or None

        # Build clean execution parameters
        exec_params: Dict[str, Any] = dict(parameters)
        if "name" in exec_params or action_type in ("CREATE_CARD", "CREATE_LIST"):
            exec_params["name"] = title
        if action_type == "CREATE_CARD":
            exec_params["desc"] = description
            if parameters.get("member_name"):
                exec_params["member_name"] = parameters.get("member_name")
        elif action_type == "MOVE_CARD" and (parameters.get("desc") or parameters.get("description")):
            exec_params["desc"] = description
        elif action_type == "UPDATE_CARD":
            if parameters.get("desc") or parameters.get("description") or parameters.get("new_description"):
                exec_params["desc"] = parameters.get("desc") or parameters.get("description") or parameters.get("new_description")
            if parameters.get("member_name"):
                exec_params["member_name"] = parameters.get("member_name")
        if due_date:
            exec_params["due_date"] = due_date
        if target_board_id and "board_id" not in exec_params:
            exec_params["board_id"] = target_board_id
        if list_id and "list_id" not in exec_params:
            exec_params["list_id"] = list_id

        # Compute payload hash
        payload_hash = compute_payload_hash(exec_params)

        # Expiration
        ttl_minutes = settings.PENDING_ACTION_DEFAULT_TTL_MINUTES or 30
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=ttl_minutes)

        draft = TaskDraft(
            title=title,
            description=description,
            board_name=target_board_name,
            board_id=target_board_id,
            list_name=list_name,
            list_id=list_id,
            priority=priority,
            due_date=due_date,
            parameters=exec_params,
        )

        pending_model = PendingActionModel(
            action_id=action_id,
            user_id=user_id,
            user_email=user_email,
            tool_id=tool_id,
            tool_name=tool_name,
            category=category,
            action_type=action_type,
            status=ApprovalStatus.PENDING,
            payload_hash=payload_hash,
            draft=draft,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )

        await self.repository.create(pending_model.model_dump())
        logger.info(f"Created pending action draft '{action_id}' for user '{user_id}' (tool='{tool_id}').")

        return ApprovalPreviewResponse(
            action_id=action_id,
            tool_id=tool_id,
            tool_name=tool_name,
            category=category,
            action_type=action_type,
            status=ApprovalStatus.PENDING.value,
            payload_hash=payload_hash,
            draft=TaskDraftSchema(**draft.model_dump()),
            created_at=now,
            expires_at=expires_at,
            message="Action prepared for user confirmation. No mutation has been executed yet.",
        )

    async def get_action(
        self,
        action_id: str,
        user_id: str,
        user_role: str,
    ) -> ApprovalPreviewResponse:
        """Retrieves an action draft preview by action_id, verifying user authorization and TTL."""
        action = await self.repository.get_by_action_id(action_id)
        if not action:
            raise ApprovalNotFoundError(f"Pending action '{action_id}' not found.")

        # Verify authorization
        is_admin = user_role.upper() == "ADMIN"
        if not is_admin and action.get("user_id") != user_id:
            raise ApprovalUnauthorizedError("You are not authorized to view this action draft.")

        # Check TTL expiration
        expires_at = action.get("expires_at")
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if action.get("status") == ApprovalStatus.EXPIRED.value or (
            action.get("status") == ApprovalStatus.PENDING.value and expires_at and expires_at < datetime.now(timezone.utc)
        ):
            if action.get("status") != ApprovalStatus.EXPIRED.value:
                await self.repository.update(action_id, {"status": ApprovalStatus.EXPIRED.value})
            raise ApprovalExpiredError(f"Action draft '{action_id}' has expired.")

        return ApprovalPreviewResponse(
            action_id=action["action_id"],
            tool_id=action["tool_id"],
            tool_name=action.get("tool_name", "Tool"),
            category=action.get("category", "TRELLO"),
            action_type=action.get("action_type", "MUTATION"),
            status=action.get("status", ApprovalStatus.PENDING.value),
            payload_hash=action.get("payload_hash", ""),
            draft=TaskDraftSchema(**action["draft"]),
            created_at=action["created_at"],
            expires_at=action["expires_at"],
            message=action.get("message", "Draft details."),
            execution_result=action.get("execution_result"),
        )

    async def confirm_action(
        self,
        action_id: str,
        user_id: str,
        user_role: str,
    ) -> ApprovalConfirmResponse:
        """
        Atomically locks and executes an approved action draft via ToolExecutorService.
        Guarantees idempotency and race condition protection against duplicate confirmations.
        """
        action = await self.repository.get_by_action_id(action_id)
        if not action:
            raise ApprovalNotFoundError(f"Pending action '{action_id}' not found.")

        # Verify authorization
        is_admin = user_role.upper() == "ADMIN"
        if not is_admin and action.get("user_id") != user_id:
            raise ApprovalUnauthorizedError("You are not authorized to confirm this action.")

        # Check TTL expiration
        expires_at = action.get("expires_at")
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at and expires_at < datetime.now(timezone.utc):
            await self.repository.update(action_id, {"status": ApprovalStatus.EXPIRED.value})
            raise ApprovalExpiredError(f"Action draft '{action_id}' has expired and cannot be confirmed.")

        # Atomic lock: transition PENDING -> EXECUTING
        locked = await self.repository.transition_status_atomically(
            action_id=action_id,
            from_status=ApprovalStatus.PENDING.value,
            to_status=ApprovalStatus.EXECUTING.value,
        )
        if not locked:
            current_status = action.get("status")
            raise ApprovalAlreadyProcessedError(
                f"Action '{action_id}' is already in '{current_status}' state and cannot be re-confirmed."
            )

        # Execute via ToolExecutorService with confirmed=True
        exec_context = ExecutionContext(
            user_id=user_id,
            user_role=user_role,
            confirmed=True,
            action_id=action_id,
        )

        draft_params = locked.get("draft", {}).get("parameters", {})
        tool_id = locked.get("tool_id")

        try:
            exec_result = await self.tool_executor.execute(
                tool_id=tool_id,
                parameters=draft_params,
                context=exec_context,
            )
        except Exception as exc:
            logger.error(f"Execution failed for action '{action_id}': {exc}")
            await self.repository.update(
                action_id,
                {
                    "status": ApprovalStatus.FAILED.value,
                    "execution_result": {"error": str(exc)},
                },
            )
            raise ApprovalExecutionError(f"Execution failed for action '{action_id}': {str(exc)}") from exc

        # Extract result metadata
        res_data = exec_result.result if hasattr(exec_result, "result") else exec_result
        if hasattr(exec_result, "model_dump"):
            dumped_result = exec_result.model_dump()
        elif isinstance(exec_result, dict):
            dumped_result = exec_result
        elif action_type in ("ARCHIVE_CARD", "DELETE_CARD"):
            description = f"Permanently archive / delete card '{title}' from Trello board."
        else:
            dumped_result = {"status": "SUCCESS", "raw": str(exec_result)}

        card_url = None
        card_id = None
        if isinstance(res_data, dict):
            card_obj = res_data.get("card") if isinstance(res_data.get("card"), dict) else res_data
            card_url = card_obj.get("url") or card_obj.get("shortUrl")
            card_id = card_obj.get("id")

        # Update MongoDB with EXECUTED
        await self.repository.update(
            action_id,
            {
                "status": ApprovalStatus.EXECUTED.value,
                "execution_result": dumped_result,
            },
        )
        logger.info(f"Action '{action_id}' successfully executed. Card URL: {card_url}")

        return ApprovalConfirmResponse(
            action_id=action_id,
            status=ApprovalStatus.EXECUTED.value,
            tool_id=tool_id,
            card_id=card_id,
            card_url=card_url,
            execution_result=dumped_result,
            message="Action confirmed and executed successfully.",
        )

    async def edit_action(
        self,
        action_id: str,
        user_id: str,
        user_role: str,
        edit_data: ApprovalEditRequest,
    ) -> ApprovalPreviewResponse:
        """Edits an existing PENDING action draft, recomputes the payload hash, and updates MongoDB."""
        action = await self.repository.get_by_action_id(action_id)
        if not action:
            raise ApprovalNotFoundError(f"Pending action '{action_id}' not found.")

        # Verify authorization
        is_admin = user_role.upper() == "ADMIN"
        if not is_admin and action.get("user_id") != user_id:
            raise ApprovalUnauthorizedError("You are not authorized to edit this action draft.")

        # Verify pending state
        if action.get("status") != ApprovalStatus.PENDING.value:
            raise ApprovalAlreadyProcessedError(
                f"Action '{action_id}' is in '{action.get('status')}' state and cannot be modified."
            )

        # Check TTL expiration
        expires_at = action.get("expires_at")
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at and expires_at < datetime.now(timezone.utc):
            await self.repository.update(action_id, {"status": ApprovalStatus.EXPIRED.value})
            raise ApprovalExpiredError(f"Action draft '{action_id}' has expired.")

        # Update draft fields
        draft = action.get("draft", {})
        params = draft.get("parameters", {})

        if edit_data.title is not None:
            draft["title"] = edit_data.title
            params["name"] = edit_data.title
        if edit_data.description is not None:
            draft["description"] = edit_data.description
            params["desc"] = edit_data.description
        if edit_data.board_name is not None:
            draft["board_name"] = edit_data.board_name
        if edit_data.board_id is not None:
            draft["board_id"] = edit_data.board_id
            params["board_id"] = edit_data.board_id
        if edit_data.list_name is not None:
            draft["list_name"] = edit_data.list_name
        if edit_data.list_id is not None:
            draft["list_id"] = edit_data.list_id
            params["list_id"] = edit_data.list_id
        if edit_data.priority is not None:
            draft["priority"] = edit_data.priority.upper()
        if edit_data.due_date is not None:
            draft["due_date"] = edit_data.due_date
            params["due_date"] = edit_data.due_date

        draft["parameters"] = params
        new_payload_hash = compute_payload_hash(params)

        updated_doc = await self.repository.update(
            action_id,
            {
                "draft": draft,
                "payload_hash": new_payload_hash,
            },
        )

        logger.info(f"Updated pending action draft '{action_id}'. New hash: {new_payload_hash}")

        return ApprovalPreviewResponse(
            action_id=action_id,
            tool_id=action["tool_id"],
            tool_name=action.get("tool_name", "Tool"),
            category=action.get("category", "TRELLO"),
            action_type=action.get("action_type", "MUTATION"),
            status=ApprovalStatus.PENDING.value,
            payload_hash=new_payload_hash,
            draft=TaskDraftSchema(**draft),
            created_at=action["created_at"],
            expires_at=action["expires_at"],
            message="Task draft updated successfully. Awaiting confirmation.",
        )

    async def cancel_action(
        self,
        action_id: str,
        user_id: str,
        user_role: str,
    ) -> ApprovalCancelResponse:
        """Cancels a pending action draft, moving status atomically to REJECTED."""
        action = await self.repository.get_by_action_id(action_id)
        if not action:
            raise ApprovalNotFoundError(f"Pending action '{action_id}' not found.")

        # Verify authorization
        is_admin = user_role.upper() == "ADMIN"
        if not is_admin and action.get("user_id") != user_id:
            raise ApprovalUnauthorizedError("You are not authorized to cancel this action draft.")

        # Atomic transition PENDING -> REJECTED
        locked = await self.repository.transition_status_atomically(
            action_id=action_id,
            from_status=ApprovalStatus.PENDING.value,
            to_status=ApprovalStatus.REJECTED.value,
        )
        if not locked:
            raise ApprovalAlreadyProcessedError(
                f"Action '{action_id}' is already in '{action.get('status')}' state and cannot be cancelled."
            )

        logger.info(f"Cancelled action draft '{action_id}' for user '{user_id}'.")
        return ApprovalCancelResponse(
            action_id=action_id,
            status=ApprovalStatus.REJECTED.value,
            message="Action has been rejected and discarded.",
        )
