from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel
from app.core.logging import logger


async def create_database_indexes(db: AsyncIOMotorDatabase) -> None:
    """Creates database indexes for core application collections."""
    try:
        # Users collection indexes
        user_indexes = [
            IndexModel([("email", ASCENDING)], unique=True, name="idx_users_email_unique"),
            IndexModel([("role", ASCENDING)], name="idx_users_role"),
            IndexModel([("is_active", ASCENDING)], name="idx_users_is_active"),
            IndexModel([("created_at", DESCENDING)], name="idx_users_created_at"),
        ]
        await db["users"].create_indexes(user_indexes)

        # Refresh tokens collection indexes
        token_indexes = [
            IndexModel([("token_hash", ASCENDING)], unique=True, name="idx_refresh_token_hash_unique"),
            IndexModel([("user_id", ASCENDING)], name="idx_refresh_tokens_user_id"),
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="idx_refresh_tokens_ttl"),
            IndexModel([("is_revoked", ASCENDING)], name="idx_refresh_tokens_is_revoked"),
        ]
        await db["refresh_tokens"].create_indexes(token_indexes)

        # Tools collection indexes (Phase 4)
        tool_indexes = [
            IndexModel([("tool_id", ASCENDING)], unique=True, name="idx_tools_tool_id_unique"),
            IndexModel([("name", ASCENDING)], unique=True, name="idx_tools_name_unique"),
            IndexModel([("category", ASCENDING)], name="idx_tools_category"),
            IndexModel([("enabled", ASCENDING)], name="idx_tools_enabled"),
            IndexModel([("created_at", DESCENDING)], name="idx_tools_created_at"),
        ]
        await db["tools"].create_indexes(tool_indexes)

        # Pending Actions collection indexes (Phase 6)
        action_indexes = [
            IndexModel([("action_id", ASCENDING)], unique=True, name="idx_pending_actions_action_id_unique"),
            IndexModel([("user_id", ASCENDING)], name="idx_pending_actions_user_id"),
            IndexModel([("status", ASCENDING)], name="idx_pending_actions_status"),
            IndexModel([("payload_hash", ASCENDING)], name="idx_pending_actions_payload_hash"),
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="idx_pending_actions_ttl"),
            IndexModel([("created_at", DESCENDING)], name="idx_pending_actions_created_at"),
        ]
        await db["pending_actions"].create_indexes(action_indexes)

        # MCP Servers collection indexes (Phase 4B/5)
        server_indexes = [
            IndexModel([("server_id", ASCENDING)], unique=True, name="idx_mcp_servers_server_id_unique"),
            IndexModel([("enabled", ASCENDING)], name="idx_mcp_servers_enabled"),
            IndexModel([("created_at", DESCENDING)], name="idx_mcp_servers_created_at"),
        ]
        await db["mcp_servers"].create_indexes(server_indexes)

        # Chat Messages collection indexes (Phase 7A Persistent Conversation)
        chat_indexes = [
            IndexModel([("user_id", ASCENDING)], name="idx_chat_messages_user_id"),
            IndexModel([("created_at", ASCENDING)], name="idx_chat_messages_created_at"),
        ]
        await db["chat_messages"].create_indexes(chat_indexes)

        # Task Assignments collection indexes (Module 1 & 6)
        task_assignment_indexes = [
            IndexModel([("employee_id", ASCENDING)], name="idx_task_assignments_employee_id"),
            IndexModel([("project_manager_id", ASCENDING)], name="idx_task_assignments_pm_id"),
            IndexModel([("board_id", ASCENDING)], name="idx_task_assignments_board_id"),
            IndexModel([("trello_card_id", ASCENDING)], name="idx_task_assignments_card_id"),
            IndexModel([("status", ASCENDING)], name="idx_task_assignments_status"),
            IndexModel([("due_date", ASCENDING)], name="idx_task_assignments_due_date"),
            IndexModel([("employee_id", ASCENDING), ("status", ASCENDING)], name="idx_task_assignments_emp_status"),
            IndexModel([("board_id", ASCENDING), ("status", ASCENDING)], name="idx_task_assignments_board_status"),
        ]
        await db["task_assignments"].create_indexes(task_assignment_indexes)

        # Task Assignment History collection indexes (Module 1 & 6)
        history_indexes = [
            IndexModel([("assignment_id", ASCENDING)], name="idx_task_history_assignment_id"),
            IndexModel([("timestamp", DESCENDING)], name="idx_task_history_timestamp"),
        ]
        await db["task_assignment_history"].create_indexes(history_indexes)

        # Employee Performance collection indexes (Module 4 & 6)
        perf_indexes = [
            IndexModel([("employee_id", ASCENDING)], unique=True, name="idx_employee_performance_emp_id_unique"),
            IndexModel([("calculated_at", DESCENDING)], name="idx_employee_performance_calculated_at"),
        ]
        await db["employee_performance"].create_indexes(perf_indexes)

        # Employee Level History collection indexes (Module 4 & 6)
        level_history_indexes = [
            IndexModel([("employee_id", ASCENDING)], name="idx_employee_level_history_emp_id"),
            IndexModel([("calculated_at", DESCENDING)], name="idx_employee_level_history_calculated_at"),
        ]
        await db["employee_level_history"].create_indexes(level_history_indexes)

        # Reminder Logs collection indexes (Module 5 & 6)
        reminder_indexes = [
            IndexModel([("assignment_id", ASCENDING), ("due_date_version", ASCENDING)], unique=True, name="idx_reminder_logs_assign_ver_unique"),
            IndexModel([("trello_card_id", ASCENDING)], name="idx_reminder_logs_trello_card_id"),
            IndexModel([("created_at", DESCENDING)], name="idx_reminder_logs_created_at"),
        ]
        await db["reminder_logs"].create_indexes(reminder_indexes)

        logger.info("Database indexes for core collections and task assignment / performance successfully ensured.")
    except Exception as e:
        logger.warning(f"Warning while ensuring database indexes: {e}")
