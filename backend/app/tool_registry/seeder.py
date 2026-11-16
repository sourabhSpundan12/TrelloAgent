from typing import List
from app.schemas.tool import ToolCategory, ToolDefinitionCreate


DEFAULT_TOOLS: List[ToolDefinitionCreate] = [
    ToolDefinitionCreate(
        name="trello_create_card",
        description="Creates a new task card on the Trello board under a designated list.",
        category=ToolCategory.TRELLO,
        version="1.0.0",
        required_permissions=["write"],
        is_mutation=True,
        requires_approval=True,
        executor_key="trello_create_card",
        tags=["card", "create", "new", "task", "trello", "add", "todo"],
        parameters_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The title or headline of the task card to create."
                },
                "list_name": {
                    "type": "string",
                    "description": "Target list name (TODO, IN_PROGRESS, IN_REVIEW, DONE). Defaults to TODO.",
                    "default": "TODO"
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description or requirements for the card."
                },
                "due_date": {
                    "type": "string",
                    "description": "Optional due date in ISO 8601 format (YYYY-MM-DD)."
                },
                "member_name": {
                    "type": "string",
                    "description": "Optional name of employee or team member to assign."
                }
            },
            "required": ["name"]
        }
    ),
    ToolDefinitionCreate(
        name="trello_move_card",
        description="Moves a card to another status list (e.g. TODO, IN_PROGRESS, IN_REVIEW, DONE).",
        category=ToolCategory.TRELLO,
        version="1.0.0",
        required_permissions=["write"],
        is_mutation=True,
        requires_approval=True,
        executor_key="trello_move_card",
        tags=["card", "move", "transition", "status", "progress", "done", "review", "in_progress"],
        parameters_schema={
            "type": "object",
            "properties": {
                "card_title": {
                    "type": "string",
                    "description": "Title of the card to identify and move."
                },
                "card_id": {
                    "type": "string",
                    "description": "Explicit Trello card ID if already known."
                },
                "target_list": {
                    "type": "string",
                    "description": "Target destination list: TODO, IN_PROGRESS, IN_REVIEW, or DONE.",
                    "enum": ["TODO", "IN_PROGRESS", "IN_REVIEW", "DONE"]
                }
            },
            "required": ["target_list"]
        }
    ),
    ToolDefinitionCreate(
        name="trello_update_card",
        description="Updates title, description, or due date of an existing card on Trello.",
        category=ToolCategory.TRELLO,
        version="1.0.0",
        required_permissions=["write"],
        is_mutation=True,
        requires_approval=True,
        executor_key="trello_update_card",
        tags=["card", "update", "edit", "modify", "rename", "change"],
        parameters_schema={
            "type": "object",
            "properties": {
                "card_title": {
                    "type": "string",
                    "description": "Title of the card to find."
                },
                "card_id": {
                    "type": "string",
                    "description": "Card ID if known."
                },
                "new_title": {
                    "type": "string",
                    "description": "Updated title for the card."
                },
                "new_description": {
                    "type": "string",
                    "description": "Updated description content."
                },
                "new_due_date": {
                    "type": "string",
                    "description": "Updated due date in ISO 8601 (YYYY-MM-DD)."
                }
            }
        }
    ),
    ToolDefinitionCreate(
        name="trello_delete_card",
        description="Deletes or archives a card from Trello.",
        category=ToolCategory.TRELLO,
        version="1.0.0",
        required_permissions=["write", "admin"],
        is_mutation=True,
        requires_approval=True,
        executor_key="trello_delete_card",
        tags=["card", "delete", "remove", "archive", "destroy"],
        parameters_schema={
            "type": "object",
            "properties": {
                "card_title": {
                    "type": "string",
                    "description": "Title of the card to delete."
                },
                "card_id": {
                    "type": "string",
                    "description": "Card ID to delete."
                }
            }
        }
    ),
    ToolDefinitionCreate(
        name="trello_search_cards",
        description="Searches for cards matching keywords, status, or assignee.",
        category=ToolCategory.TRELLO,
        version="1.0.0",
        required_permissions=["read"],
        is_mutation=False,
        requires_approval=False,
        executor_key="trello_search_cards",
        tags=["search", "find", "cards", "lookup", "query", "filter"],
        parameters_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword to match against card titles."
                },
                "status": {
                    "type": "string",
                    "description": "Status filter: TODO, IN_PROGRESS, IN_REVIEW, DONE."
                },
                "assignee": {
                    "type": "string",
                    "description": "Filter by assigned employee name."
                }
            }
        }
    ),
    ToolDefinitionCreate(
        name="trello_get_card_details",
        description="Retrieves full metadata and historical state changes for a specific card.",
        category=ToolCategory.TRELLO,
        version="1.0.0",
        required_permissions=["read"],
        is_mutation=False,
        requires_approval=False,
        executor_key="trello_get_card_details",
        tags=["details", "card", "get", "view", "inspect", "history"],
        parameters_schema={
            "type": "object",
            "properties": {
                "card_title": {
                    "type": "string",
                    "description": "Title of card."
                },
                "card_id": {
                    "type": "string",
                    "description": "ID of card."
                }
            }
        }
    ),
    ToolDefinitionCreate(
        name="report_get_workload",
        description="Generates daily, weekly, or date-range workload summaries and task counts by status.",
        category=ToolCategory.REPORTING,
        version="1.0.0",
        required_permissions=["read"],
        is_mutation=False,
        requires_approval=False,
        executor_key="report_get_workload",
        tags=["report", "workload", "employee", "team", "metrics", "analytics", "stats", "weekly", "daily"],
        parameters_schema={
            "type": "object",
            "properties": {
                "report_type": {
                    "type": "string",
                    "enum": ["daily", "weekly", "custom"],
                    "default": "daily",
                    "description": "Time window type."
                },
                "employee_id": {
                    "type": "string",
                    "description": "Optional filter for specific employee."
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date for custom range (YYYY-MM-DD)."
                },
                "end_date": {
                    "type": "string",
                    "description": "End date for custom range (YYYY-MM-DD)."
                }
            }
        }
    ),
    ToolDefinitionCreate(
        name="report_get_employee_tasks",
        description="Distinguishes assigned employees from employees actively working on IN_PROGRESS tasks.",
        category=ToolCategory.EMPLOYEE,
        version="1.0.0",
        required_permissions=["read"],
        is_mutation=False,
        requires_approval=False,
        executor_key="report_get_employee_tasks",
        tags=["employee", "tasks", "assigned", "in_progress", "active", "workload"],
        parameters_schema={
            "type": "object",
            "properties": {
                "employee_name": {
                    "type": "string",
                    "description": "Employee name or identifier."
                },
                "status_filter": {
                    "type": "string",
                    "description": "Optional status filter (TODO, IN_PROGRESS, IN_REVIEW, DONE)."
                }
            }
        }
    )
]

