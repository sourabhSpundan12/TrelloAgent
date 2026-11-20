from datetime import datetime, timedelta, timezone
import re
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
    def _generate_related_description(title: str, command: str, raw_desc: Optional[str] = None) -> str:
        clean_title = title.strip()
        t_lower = clean_title.lower()

        # If user explicitly supplied custom description text in quotes or after 'description:' or 'notes:'
        # and it's NOT an echo of the "create card ... by ... add member" prompt:
        if raw_desc and str(raw_desc).strip():
            d_clean = str(raw_desc).strip()
            d_lower = d_clean.lower()
            is_echo = (
                re.match(r"^(?:create|add|new)\s+(?:a\s+)?(?:task\s+card|card|task)\b", d_lower)
                or ("with due date" in d_lower and ("assigned to" in d_lower or "add member" in d_lower))
                or d_lower.startswith("create ")
                or ("due date" in d_lower and "assigned to" in d_lower)
                or "task created via agentic assistant" in d_lower
                or (command and d_clean.lower() == command.lower())
            )
            if not is_echo:
                return d_clean

        # Intelligent domain-aware descriptions directly aligned with the title
        if any(k in t_lower for k in ("backend", "server", "api", "endpoint", "microservice")):
            return (
                f"Design, develop, and test backend architecture, API endpoints, database interactions, and business logic for '{clean_title}'. "
                "Ensure robust error handling, schema validation, performance optimization, and comprehensive unit test coverage."
            )
        elif any(k in t_lower for k in ("frontend", "ui", "ux", "web", "react", "view", "interface", "page")):
            return (
                f"Build and refine responsive user interface components and client-side interactions for '{clean_title}'. "
                "Ensure accessibility standards, seamless backend API integration, state management, and cross-browser reliability."
            )
        elif any(k in t_lower for k in ("auth", "login", "register", "signup", "password", "jwt", "oauth")):
            return (
                f"Implement secure authentication workflows, credential hashing, token lifecycle, and session verification for '{clean_title}'. "
                "Enforce role-based access control, route protection, and security audit compliance."
            )
        elif any(k in t_lower for k in ("database", "db", "mongo", "postgres", "sql", "migration", "schema")):
            return (
                f"Design and optimize data models, collections, indexes, and persistence layers for '{clean_title}'. "
                "Ensure transactional integrity, migration reliability, query efficiency, and backup readiness."
            )
        elif any(k in t_lower for k in ("test", "testing", "qa", "e2e", "integration test")):
            return (
                f"Develop and execute automated test suites, end-to-end verification, and edge-case assertions for '{clean_title}'. "
                "Identify potential defects, verify regression safety, and validate system stability under expected workloads."
            )
        elif any(k in t_lower for k in ("deploy", "devops", "docker", "k8s", "kubernetes", "ci", "cd", "pipeline", "infrastructure")):
            return (
                f"Configure deployment infrastructure, build pipelines, environment variables, and health monitoring for '{clean_title}'. "
                "Ensure zero-downtime rollouts, security hardening, and operational observability."
            )
        elif any(k in t_lower for k in ("checkin", "status", "standup", "sync", "review")):
            return (
                f"Conduct milestone progress review and status synchronization for '{clean_title}'. "
                "Track sprint deliverables against timeline, align dependencies, and document action items."
            )
        elif any(k in t_lower for k in ("bug", "fix", "issue", "error", "hotfix")):
            return (
                f"Investigate root cause of reported issue in '{clean_title}', develop and test code fix, and verify regression safety before deploying to production."
            )
        elif any(k in t_lower for k in ("doc", "docs", "documentation", "guide", "readme")):
            return (
                f"Author and update technical documentation, system specifications, architectural diagrams, and user guidelines for '{clean_title}'."
            )
        else:
            return (
                f"Plan, implement, and verify deliverables for '{clean_title}'. "
                "Review project requirements, execute core development milestones, and validate against quality and acceptance standards."
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
        target_board_name = board_name
        if not target_board_name and target_board_id:
            try:
                b_doc = await self.db["boards"].find_one({"$or": [{"board_id": target_board_id}, {"id": target_board_id}]})
                if b_doc and b_doc.get("name"):
                    target_board_name = b_doc["name"]
            except Exception:
                pass
        if not target_board_name:
            target_board_name = "Configured Trello Board"

        # Resolve list
        list_name = (
            parameters.get("list_name")
            or parameters.get("target_status")
            or "To Do"
        )
        list_id = parameters.get("list_id")

        # Resolve description
        is_bulk_delete = (
            action_type == "DELETE_LIST_CARDS"
            or parameters.get("is_bulk_delete")
            or (action_type in ("ARCHIVE_CARD", "DELETE_CARD") and "all" in command.lower() and any(w in command.lower() for w in ["task", "tasks", "card", "cards"]))
        )
        if is_bulk_delete:
            action_type = "DELETE_LIST_CARDS"
            raw_target = str(parameters.get("list_name") or parameters.get("card_name") or parameters.get("name") or "").strip()
            raw_target = re.sub(r"^(?:of|in|from|under)\s+", "", raw_target, flags=re.IGNORECASE).strip()
            clean_list_name = re.sub(r"\s+(?:list|column)$", "", raw_target, flags=re.IGNORECASE).strip()
            if not clean_list_name or clean_list_name.lower() in ("task", "tasks", "card", "cards", "all"):
                clean_list_name = "To Do"

            resolved_list_name = clean_list_name
            resolved_list_id = list_id
            cards_in_list = []
            try:
                from app.mcp_server import trello_tools
                lists_res = await trello_tools.trello_list_lists(board_id=target_board_id)
                board_lists = lists_res.get("lists", [])
                norm_target = re.sub(r"[\s\-_]+", "", clean_list_name.lower())
                matched_list = None
                for bl in board_lists:
                    bl_norm = re.sub(r"[\s\-_]+", "", bl.get("name", "").lower())
                    if norm_target == bl_norm or norm_target in bl_norm or bl_norm in norm_target:
                        matched_list = bl
                        break
                if matched_list:
                    resolved_list_name = matched_list.get("name", clean_list_name)
                    resolved_list_id = matched_list.get("id")
                    cards_res = await trello_tools.trello_list_cards(board_id=target_board_id, list_id=resolved_list_id)
                    cards_in_list = cards_res.get("cards", [])
            except Exception as exc:
                logger.debug(f"Could not load live cards for bulk delete preview: {exc}")

            cards_count = len(cards_in_list)
            card_names = [c.get("name", "Card") for c in cards_in_list]
            card_ids = [c.get("id") for c in cards_in_list]

            title = f"Delete all tasks in '{resolved_list_name}'"
            description = (
                f"Permanently archive / delete {cards_count} task(s) currently in '{resolved_list_name}' list from Trello board."
                if cards_count > 0
                else f"Permanently archive / delete tasks in '{resolved_list_name}' list from Trello board (list is currently empty)."
            )
            list_name = resolved_list_name
            list_id = resolved_list_id
        elif action_type == "CREATE_LIST":
            description = f"Create new column/list '{title}' on the board."
        elif action_type == "MOVE_CARD":
            raw_desc = parameters.get("desc") or parameters.get("description")
            has_explicit_desc = bool(
                raw_desc
                and "task created via agentic assistant" not in str(raw_desc).lower()
                and not str(raw_desc).lower().startswith("move card")
                and str(raw_desc).strip() != ""
            )
            if has_explicit_desc:
                description = str(raw_desc).strip()
            else:
                # User did not provide a new description: retain existing card description
                existing_card_desc = None
                try:
                    from app.mcp_server import trello_tools
                    cards_res = await trello_tools.trello_list_cards(board_id=target_board_id)
                    title_norm = title.lower().strip()
                    for c in cards_res.get("cards", []):
                        c_name = c.get("name", "").lower().strip()
                        if c_name == title_norm or title_norm in c_name:
                            existing_card_desc = c.get("desc")
                            break
                except Exception:
                    pass

                if not existing_card_desc and self.db is not None:
                    try:
                        t_doc = await self.db["task_assignments"].find_one(
                            {"task_title": {"$regex": f"^{re.escape(title)}$", "$options": "i"}}
                        )
                        if t_doc and t_doc.get("task_description"):
                            existing_card_desc = t_doc["task_description"]
                    except Exception:
                        pass

                description = existing_card_desc.strip() if existing_card_desc else ""
        elif action_type == "UPDATE_CARD":
            raw_desc = parameters.get("desc") or parameters.get("description") or parameters.get("new_description")
            member_name = parameters.get("member_name") or parameters.get("assignee")
            new_due = parameters.get("new_due_date") or parameters.get("due_date") or parameters.get("due") or parameters.get("date")
            new_title_param = parameters.get("new_name") or parameters.get("new_title")

            updates = []
            if new_title_param:
                updates.append(f"rename to '{new_title_param}'")
            if new_due:
                updates.append(f"set due date to '{new_due}'")
            if member_name:
                updates.append(f"assign member '{member_name}'")
            if raw_desc and "task created via agentic assistant" not in str(raw_desc).lower() and str(raw_desc).strip() != "":
                updates.append(f"update notes to '{raw_desc}'")

            if updates:
                description = f"Update card '{title}': {', '.join(updates)}."
            else:
                description = f"Update card '{title}' on the board."
        elif action_type in ("ARCHIVE_CARD", "DELETE_CARD"):
            raw_target = title.strip()
            if parameters.get("list_name") or any(k in raw_target.lower() for k in ("guide", "list", "column", "starter", "started", "tasks")):
                description = f"Permanently archive / delete task cards in '{raw_target}' list from Trello board."
            else:
                description = f"Permanently archive / delete card '{title}' from Trello board."
        else:
            raw_desc = parameters.get("desc") or parameters.get("description")
            description = self._generate_related_description(title, command, raw_desc)

        # Resolve priority & due date
        priority = (parameters.get("priority") or "MEDIUM").upper()
        due_date = (
            parameters.get("due_date")
            or parameters.get("new_due_date")
            or parameters.get("due")
            or parameters.get("date")
            or None
        )
        if is_bulk_delete:
            priority = "URGENT" if cards_count > 0 else "HIGH"
            due_date = None

        # Build clean execution parameters
        exec_params: Dict[str, Any] = dict(parameters)
        if is_bulk_delete:
            exec_params["list_name"] = resolved_list_name
            exec_params["card_name"] = resolved_list_name
            exec_params["name"] = resolved_list_name
            exec_params["list_id"] = resolved_list_id
            exec_params["cards_count"] = cards_count
            exec_params["card_names"] = card_names
            exec_params["card_ids"] = card_ids
            exec_params["is_bulk_delete"] = True
            exec_params["action_type"] = "DELETE_LIST_CARDS"
        if "name" in exec_params or action_type in ("CREATE_CARD", "CREATE_LIST"):
            exec_params["name"] = title
        if action_type == "CREATE_CARD":
            exec_params["desc"] = description
            if parameters.get("member_name"):
                exec_params["member_name"] = parameters.get("member_name")
        elif action_type == "MOVE_CARD":
            if has_explicit_desc:
                exec_params["desc"] = description
            else:
                exec_params.pop("desc", None)
                exec_params.pop("description", None)
        elif action_type == "UPDATE_CARD":
            if parameters.get("desc") or parameters.get("description") or parameters.get("new_description"):
                exec_params["desc"] = parameters.get("desc") or parameters.get("description") or parameters.get("new_description")
            if parameters.get("member_name"):
                exec_params["member_name"] = parameters.get("member_name")
            if due_date:
                exec_params["new_due_date"] = due_date
                exec_params["due_date"] = due_date
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

        draft_params = dict(locked.get("draft", {}).get("parameters", {}))
        board_id_val = locked.get("draft", {}).get("board_id") or locked.get("board_id")
        if board_id_val and "board_id" not in draft_params:
            draft_params["board_id"] = board_id_val
        due_val = locked.get("draft", {}).get("due_date") or locked.get("due_date")
        if due_val and not draft_params.get("due_date") and not draft_params.get("due"):
            draft_params["due_date"] = due_val
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
            raw_target = title.strip()
            if parameters.get("list_name") or any(k in raw_target.lower() for k in ("guide", "list", "column", "starter", "started", "tasks")):
                description = f"Permanently archive / delete task cards in '{raw_target}' list from Trello board."
            else:
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

        # Module 1 auto-correlation: If this created/assigned a card to a team member, record task assignment
        member_name = draft_params.get("member_name")
        if member_name and card_id:
            try:
                from app.services.task_assignment_service import TaskAssignmentService
                from app.integrations.trello.client import parse_due_date_for_trello
                emp = await self.db["users"].find_one({
                    "$or": [
                        {"full_name": {"$regex": f"^{re.escape(member_name.strip())}$", "$options": "i"}},
                        {"full_name": {"$regex": re.escape(member_name.strip()), "$options": "i"}},
                        {"email": {"$regex": re.escape(member_name.strip()), "$options": "i"}},
                    ]
                })
                if emp:
                    emp_id = str(emp["_id"])
                    existing_ass = await self.db["task_assignments"].find_one({"trello_card_id": card_id})
                    if not existing_ass:
                        due_dt = None
                        if due_val:
                            iso_str = parse_due_date_for_trello(due_val)
                            if iso_str:
                                due_dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))

                        await TaskAssignmentService.create_assignment(
                            db=self.db,
                            employee_id=emp_id,
                            project_manager_id=user_id,
                            board_id=board_id_val or "default",
                            trello_card_id=card_id,
                            task_title=locked.get("draft", {}).get("title") or draft_params.get("name") or "Assigned Task",
                            task_description=locked.get("draft", {}).get("description"),
                            due_date=due_dt,
                            board_name=locked.get("draft", {}).get("board_name"),
                            trello_card_url=card_url,
                            employee_name=emp.get("full_name"),
                            employee_email=emp.get("email"),
                        )
            except Exception as e:
                logger.warning(f"Could not auto-create task assignment for card {card_id}: {e}")

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
