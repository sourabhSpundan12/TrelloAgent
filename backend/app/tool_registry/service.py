from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import logger
from app.tool_registry.models import ToolModel
from app.tool_registry.repository import ToolRepository
from app.tool_registry.schemas import (
    ToolListResponse,
    ToolRegisterRequest,
    ToolResponse,
    ToolUpdateRequest,
)
from app.tool_registry.validators import validate_input_schema, validate_tool_metadata


DEFAULT_ENTERPRISE_TOOLS: List[Dict[str, Any]] = [
    {
        "tool_id": "trello_create_card",
        "name": "Create Trello Card",
        "description": "Creates a new task card on the Trello board under a designated list (TODO, IN_PROGRESS, IN_REVIEW, DONE).",
        "category": "trello",
        "keywords": ["card", "create", "new", "task", "trello", "add card", "todo", "issue", "ticket"],
        "synonyms": ["add a card", "create a task", "post a card", "make a ticket", "new item"],
        "capabilities": ["create_card", "task_creation", "board_management"],
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The title or headline of the task card to create."},
                "list_name": {
                    "type": "string",
                    "description": "Target list name (TODO, IN_PROGRESS, IN_REVIEW, DONE). Defaults to TODO.",
                    "default": "TODO",
                },
                "description": {"type": "string", "description": "Detailed description or requirements for the card."},
                "due_date": {"type": "string", "description": "Optional due date in ISO 8601 format (YYYY-MM-DD)."},
                "member_name": {"type": "string", "description": "Optional name of employee or team member to assign."},
            },
            "required": ["name"],
        },
        "permissions": ["EMPLOYEE", "MANAGER", "ADMIN"],
        "executor_type": "trello",
        "executor_key": "trello_create_card",
        "version": "1.0.0",
        "enabled": True,
        "approval_required": True,
    },
    {
        "tool_id": "trello_create_list",
        "name": "Create Trello List",
        "description": "Creates a new list or column on the Trello board (e.g. In-Review, Backlog, Testing).",
        "category": "trello",
        "keywords": ["list", "column", "create", "add", "trello", "new list", "new column"],
        "synonyms": ["add a list", "create a column", "make a list", "new list", "add column"],
        "capabilities": ["create_list", "board_management"],
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The name of the new list or column (e.g. In-Review)."},
                "board_id": {"type": "string", "description": "Optional board ID."},
                "pos": {"type": "string", "description": "Position on board: 'top', 'bottom', or numeric.", "default": "bottom"},
            },
            "required": ["name"],
        },
        "permissions": ["EMPLOYEE", "MANAGER", "ADMIN"],
        "executor_type": "trello",
        "executor_key": "trello_create_list",
        "version": "1.0.0",
        "enabled": True,
        "approval_required": True,
    },
    {
        "tool_id": "trello_move_card",
        "name": "Move Trello Card",
        "description": "Moves a task card to another list or column on the Trello board (e.g. Testing, In-Review, To Do, Doing, Done, or any custom list).",
        "category": "trello",
        "keywords": ["card", "move", "transition", "status", "progress", "done", "review", "in_progress", "testing"],
        "synonyms": ["move the card", "change status", "transition task", "mark as done", "put in progress", "move to list"],
        "capabilities": ["move_card", "status_transition", "workflow_progress"],
        "input_schema": {
            "type": "object",
            "properties": {
                "card_name": {"type": "string", "description": "Title of the card to identify and move."},
                "card_id": {"type": "string", "description": "Explicit Trello card ID if already known."},
                "target_status": {
                    "type": "string",
                    "description": "Destination list or column name (e.g. Testing, In-Review, To Do, Doing, Done, or any custom list name).",
                },
                "due_date": {"type": "string", "description": "Optional due date to set or update on the card (e.g. 'tomorrow', 'next week', 'YYYY-MM-DD')."},
                "description": {"type": "string", "description": "Optional updated description content or notes for the card."},
            },
            "required": ["target_status"],
        },
        "permissions": ["EMPLOYEE", "MANAGER", "ADMIN"],
        "executor_type": "trello",
        "executor_key": "trello_move_card",
        "version": "1.0.0",
        "enabled": True,
        "approval_required": True,
    },
    {
        "tool_id": "trello_update_card",
        "name": "Update Trello Card",
        "description": "Updates the title, description, due date, or assigns a member to an existing card on Trello.",
        "category": "trello",
        "keywords": ["card", "update", "edit", "modify", "rename", "change", "member", "assign", "assignee", "add member"],
        "synonyms": ["edit card", "update task", "change description", "rename card", "assign member", "add member", "assign card to member", "add assignee"],
        "capabilities": ["update_card", "edit_task", "assign_member"],
        "input_schema": {
            "type": "object",
            "properties": {
                "card_name": {"type": "string", "description": "Title or name of the card to find and update."},
                "card_id": {"type": "string", "description": "Card ID if known."},
                "new_title": {"type": "string", "description": "Updated title for the card."},
                "new_description": {"type": "string", "description": "Updated description content."},
                "new_due_date": {"type": "string", "description": "Updated due date in ISO 8601 (YYYY-MM-DD) or relative terms."},
                "member_name": {"type": "string", "description": "Name or username of the team member or employee to assign or add to the card."},
            },
        },
        "permissions": ["EMPLOYEE", "MANAGER", "ADMIN"],
        "executor_type": "trello",
        "executor_key": "trello_update_card",
        "version": "1.0.0",
        "enabled": True,
        "approval_required": True,
    },
    {
        "tool_id": "trello_delete_card",
        "name": "Delete Trello Card",
        "description": "Deletes or archives a task card from Trello. Requires elevated permissions.",
        "category": "trello",
        "keywords": ["card", "delete", "remove", "archive", "destroy", "trash"],
        "synonyms": ["delete card", "remove task", "discard item", "archive card"],
        "capabilities": ["delete_card", "archive_task"],
        "input_schema": {
            "type": "object",
            "properties": {
                "card_name": {"type": "string", "description": "Title of the card to delete."},
                "card_id": {"type": "string", "description": "Card ID to delete."},
            },
        },
        "permissions": ["MANAGER", "ADMIN"],
        "executor_type": "trello",
        "executor_key": "trello_delete_card",
        "version": "1.0.0",
        "enabled": True,
        "approval_required": True,
    },
    {
        "tool_id": "trello_search_cards",
        "name": "Search Trello Cards",
        "description": "Searches for cards matching keywords, status (TODO, IN_PROGRESS, IN_REVIEW, DONE), or assigned employee.",
        "category": "trello",
        "keywords": ["search", "find", "cards", "lookup", "query", "filter", "list"],
        "synonyms": ["find cards", "show tasks", "search for item", "filter cards"],
        "capabilities": ["search_cards", "query_tasks", "read_board"],
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword to match against card titles."},
                "status": {"type": "string", "description": "Status filter: TODO, IN_PROGRESS, IN_REVIEW, DONE."},
                "assignee": {"type": "string", "description": "Filter by assigned employee name."},
            },
        },
        "permissions": ["EMPLOYEE", "MANAGER", "ADMIN", "HR"],
        "executor_type": "trello",
        "executor_key": "trello_search_cards",
        "version": "1.0.0",
        "enabled": True,
        "approval_required": False,
    },
    {
        "tool_id": "report_get_workload",
        "name": "Get Workload Report",
        "description": "Generates daily, weekly, or custom date-range workload summaries and task counts across teams.",
        "category": "reporting",
        "keywords": ["report", "workload", "employee", "team", "metrics", "analytics", "stats", "weekly", "daily"],
        "synonyms": ["generate report", "show workload", "team analytics", "workload summary"],
        "capabilities": ["workload_analytics", "reporting", "metrics"],
        "input_schema": {
            "type": "object",
            "properties": {
                "report_type": {
                    "type": "string",
                    "enum": ["daily", "weekly", "custom"],
                    "default": "daily",
                    "description": "Time window type.",
                },
                "start_date": {"type": "string", "description": "Start date for custom range (YYYY-MM-DD)."},
                "end_date": {"type": "string", "description": "End date for custom range (YYYY-MM-DD)."},
            },
        },
        "permissions": ["EMPLOYEE", "MANAGER", "ADMIN", "HR"],
        "executor_type": "reporting",
        "executor_key": "report_get_workload",
        "version": "1.0.0",
        "enabled": True,
        "approval_required": False,
    },
    {
        "tool_id": "report_get_employee_tasks",
        "name": "Get Employee Tasks",
        "description": "Retrieves task assignments for an employee, distinguishing assigned tasks from tasks actively IN_PROGRESS.",
        "category": "employee_management",
        "keywords": ["employee", "tasks", "assigned", "in_progress", "active", "workload", "staff"],
        "synonyms": ["show employee tasks", "what is employee working on", "staff workload"],
        "capabilities": ["employee_tasks", "individual_workload"],
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_name": {"type": "string", "description": "Employee name or identifier."},
                "status_filter": {"type": "string", "description": "Optional status filter (TODO, IN_PROGRESS, IN_REVIEW, DONE)."},
            },
        },
        "permissions": ["EMPLOYEE", "MANAGER", "ADMIN", "HR"],
        "executor_type": "employee_management",
        "executor_key": "report_get_employee_tasks",
        "version": "1.0.0",
        "enabled": True,
        "approval_required": False,
    },
    {
        "tool_id": "trello_get_card_details",
        "name": "Get Card Details",
        "description": "Retrieves complete metadata, status history, and assignment details for a specific Trello card.",
        "category": "trello",
        "keywords": ["card", "details", "inspect", "history", "view", "get", "activity"],
        "synonyms": ["view card details", "get card info", "inspect task", "show card details"],
        "capabilities": ["get_card_details", "view_history"],
        "input_schema": {
            "type": "object",
            "properties": {
                "card_name": {"type": "string", "description": "Title or name of card to inspect."},
                "card_id": {"type": "string", "description": "Optional card ID if known."},
            },
        },
        "permissions": ["EMPLOYEE", "MANAGER", "ADMIN", "HR"],
        "executor_type": "trello",
        "executor_key": "trello_get_card_details",
        "version": "1.0.0",
        "enabled": True,
        "approval_required": False,
    },
    {
        "tool_id": "employee_list_directory",
        "name": "List Employee Directory",
        "description": "Retrieves employee directory, roles, departments, and active availability status.",
        "category": "employee_management",
        "keywords": ["employee", "directory", "staff", "team", "members", "roster", "list"],
        "synonyms": ["show employees", "list team members", "staff directory", "view staff"],
        "capabilities": ["list_employees", "team_roster"],
        "input_schema": {
            "type": "object",
            "properties": {
                "department": {"type": "string", "description": "Optional department filter."},
            },
        },
        "permissions": ["EMPLOYEE", "MANAGER", "ADMIN", "HR"],
        "executor_type": "employee_management",
        "executor_key": "employee_list_directory",
        "version": "1.0.0",
        "enabled": True,
        "approval_required": False,
    },
]


class ToolRegistryService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.repo = ToolRepository(db)

    async def register_tool(self, req: ToolRegisterRequest) -> ToolResponse:
        """Register a new tool with validation and duplicate prevention."""
        validate_input_schema(req.input_schema)
        validate_tool_metadata(req.tool_id, req.name, req.version, req.executor_key)

        existing_id = await self.repo.get_by_tool_id(req.tool_id)
        if existing_id:
            raise ConflictError(f"Tool with tool_id '{req.tool_id}' already exists.")

        existing_name = await self.repo.get_by_name(req.name)
        if existing_name:
            raise ConflictError(f"Tool with name '{req.name}' already exists.")

        tool_data = req.model_dump()
        now = datetime.now(timezone.utc)
        tool_data["created_at"] = now
        tool_data["updated_at"] = now

        created = await self.repo.create(tool_data)
        logger.info(f"Registered new tool: {created['tool_id']} ({created['name']}) [v{created['version']}]")
        return ToolResponse(**created)

    async def get_tool(self, tool_id: str) -> ToolResponse:
        """Fetch tool by unique tool_id."""
        tool = await self.repo.get_by_tool_id(tool_id)
        if not tool:
            raise NotFoundError(f"Tool with tool_id '{tool_id}' not found.")
        return ToolResponse(**tool)

    async def update_tool(self, tool_id: str, req: ToolUpdateRequest) -> ToolResponse:
        """Update existing tool metadata and version."""
        existing = await self.repo.get_by_tool_id(tool_id)
        if not existing:
            raise NotFoundError(f"Tool with tool_id '{tool_id}' not found.")

        update_dict = {k: v for k, v in req.model_dump().items() if v is not None}
        if not update_dict:
            return ToolResponse(**existing)

        if "input_schema" in update_dict:
            validate_input_schema(update_dict["input_schema"])

        if "name" in update_dict and update_dict["name"] != existing["name"]:
            name_check = await self.repo.get_by_name(update_dict["name"])
            if name_check and name_check.get("tool_id") != tool_id:
                raise ConflictError(f"Tool with name '{update_dict['name']}' already exists.")

        if "version" in update_dict:
            validate_tool_metadata(tool_id, update_dict.get("name", existing["name"]), update_dict["version"], existing["executor_key"])

        updated = await self.repo.update(tool_id, update_dict)
        if not updated:
            raise NotFoundError(f"Tool with tool_id '{tool_id}' not found.")
        logger.info(f"Updated tool metadata for: {tool_id}")
        return ToolResponse(**updated)

    async def enable_tool(self, tool_id: str) -> ToolResponse:
        """Enable a tool."""
        existing = await self.repo.get_by_tool_id(tool_id)
        if not existing:
            raise NotFoundError(f"Tool with tool_id '{tool_id}' not found.")
        updated = await self.repo.set_enabled(tool_id, True)
        logger.info(f"Enabled tool: {tool_id}")
        return ToolResponse(**updated)

    async def disable_tool(self, tool_id: str) -> ToolResponse:
        """Disable a tool so it is never discoverable for execution."""
        existing = await self.repo.get_by_tool_id(tool_id)
        if not existing:
            raise NotFoundError(f"Tool with tool_id '{tool_id}' not found.")
        updated = await self.repo.set_enabled(tool_id, False)
        logger.info(f"Disabled tool: {tool_id}")
        return ToolResponse(**updated)

    async def list_tools(
        self,
        page: int = 1,
        page_size: int = 20,
        category: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> ToolListResponse:
        """List registered tools with pagination and filtering."""
        skip = (page - 1) * page_size
        tools_raw, total = await self.repo.list_tools(skip=skip, limit=page_size, category=category, enabled=enabled)
        tools = [ToolResponse(**t) for t in tools_raw]
        return ToolListResponse(
            tools=tools,
            total=total,
            page=page,
            page_size=page_size,
        )

    async def seed_default_tools(self) -> int:
        """Seed default enterprise tools if not already present or synchronize existing schemas."""
        seeded_count = 0
        for tool_data in DEFAULT_ENTERPRISE_TOOLS:
            existing = await self.repo.get_by_tool_id(tool_data["tool_id"])
            if not existing:
                await self.repo.create(tool_data.copy())
                seeded_count += 1
            else:
                # Keep input_schema and metadata synchronized
                await self.repo.collection.update_one(
                    {"tool_id": tool_data["tool_id"]},
                    {
                        "$set": {
                            "name": tool_data["name"],
                            "description": tool_data["description"],
                            "category": tool_data["category"],
                            "keywords": tool_data["keywords"],
                            "synonyms": tool_data["synonyms"],
                            "capabilities": tool_data["capabilities"],
                            "input_schema": tool_data["input_schema"],
                            "permissions": tool_data["permissions"],
                            "executor_type": tool_data["executor_type"],
                            "executor_key": tool_data["executor_key"],
                            "approval_required": tool_data["approval_required"],
                        }
                    },
                )
        if seeded_count > 0:
            logger.info(f"Seeded {seeded_count} default enterprise tools into Tool Registry.")
        return seeded_count

