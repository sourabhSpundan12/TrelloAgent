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

        logger.info("Database indexes for users, refresh_tokens, tools, pending_actions, mcp_servers, and chat_messages successfully ensured.")
    except Exception as e:
        logger.warning(f"Warning while ensuring database indexes: {e}")
