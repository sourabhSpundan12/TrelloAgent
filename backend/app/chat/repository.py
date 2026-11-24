import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase


class ChatRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db["chat_messages"]
        self.sessions_collection = db["chat_sessions"]

    async def add_message(self, message_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Saves a chat message to MongoDB Atlas and keeps conversation session metadata synced."""
        now = datetime.now(timezone.utc)
        message_dict.setdefault("created_at", now)
        conv_id = message_dict.get("conversation_id")
        user_id = message_dict.get("user_id")
        board_id = message_dict.get("board_id")

        await self.collection.insert_one(message_dict)
        message_dict.pop("_id", None)

        if conv_id and user_id:
            existing = await self.sessions_collection.find_one({"id": conv_id, "user_id": user_id})
            content_preview = str(message_dict.get("content", "")).strip()
            clean_title = re.sub(r"\s+", " ", content_preview)[:45] or "New Chat"

            if not existing:
                title = clean_title if message_dict.get("sender") == "user" else "New Chat"
                await self.sessions_collection.insert_one({
                    "id": conv_id,
                    "user_id": user_id,
                    "board_id": board_id,
                    "title": title,
                    "created_at": now,
                    "updated_at": now,
                    "message_count": 1,
                })
            else:
                update_fields: Dict[str, Any] = {
                    "updated_at": now,
                }
                if board_id and not existing.get("board_id"):
                    update_fields["board_id"] = board_id

                # If existing title is generic and a user message arrives, update title
                if existing.get("title") in ("New Chat", "New Conversation") and message_dict.get("sender") == "user" and clean_title:
                    update_fields["title"] = clean_title

                await self.sessions_collection.update_one(
                    {"id": conv_id, "user_id": user_id},
                    {
                        "$set": update_fields,
                        "$inc": {"message_count": 1},
                    },
                )

        return message_dict

    async def list_sessions(
        self, user_id: str, board_id: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Retrieves conversation sessions for a user, filtered by board_id if provided."""
        query: Dict[str, Any] = {"user_id": user_id}
        if board_id:
            query["board_id"] = board_id

        cursor = self.sessions_collection.find(query).sort("updated_at", -1).limit(limit)
        sessions = []
        async for doc in cursor:
            doc.pop("_id", None)
            sessions.append(doc)

        # Migration / backward compatibility:
        # If user has no sessions with this board_id, but has legacy sessions with no board_id,
        # we check if those legacy sessions should be associated with this initial board_id.
        if not sessions and board_id:
            legacy_count = await self.sessions_collection.count_documents(
                {"user_id": user_id, "board_id": {"$exists": False}}
            )
            all_boarded_count = await self.sessions_collection.count_documents(
                {"user_id": user_id, "board_id": {"$exists": True}}
            )
            if legacy_count > 0 and all_boarded_count == 0:
                await self.sessions_collection.update_many(
                    {"user_id": user_id, "board_id": {"$exists": False}},
                    {"$set": {"board_id": board_id}},
                )
                await self.collection.update_many(
                    {"user_id": user_id, "board_id": {"$exists": False}},
                    {"$set": {"board_id": board_id}},
                )
                cursor = self.sessions_collection.find({"user_id": user_id, "board_id": board_id}).sort("updated_at", -1).limit(limit)
                async for doc in cursor:
                    doc.pop("_id", None)
                    sessions.append(doc)

        return sessions

    async def get_history(
        self, user_id: str, conversation_id: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Retrieves user conversation history in chronological order."""
        query: Dict[str, Any] = {"user_id": user_id}
        if conversation_id:
            query["conversation_id"] = conversation_id
        cursor = self.collection.find(query).sort("created_at", 1).limit(limit)
        messages = []
        async for doc in cursor:
            doc.pop("_id", None)
            messages.append(doc)
        return messages

    async def rename_session(self, user_id: str, conversation_id: str, title: str) -> bool:
        """Renames a conversation session for a user."""
        clean_title = re.sub(r"\s+", " ", title.strip())[:60]
        now = datetime.now(timezone.utc)
        res = await self.sessions_collection.update_one(
            {"id": conversation_id, "user_id": user_id},
            {"$set": {"title": clean_title, "updated_at": now}},
        )
        return res.modified_count > 0

    async def delete_session(self, user_id: str, conversation_id: str) -> bool:
        """Deletes a conversation session and all its messages."""
        await self.collection.delete_many({"user_id": user_id, "conversation_id": conversation_id})
        res = await self.sessions_collection.delete_one({"id": conversation_id, "user_id": user_id})
        return res.deleted_count > 0

    async def clear_history(self, user_id: str) -> int:
        """Clears all conversation history and sessions for a user."""
        res = await self.collection.delete_many({"user_id": user_id})
        await self.sessions_collection.delete_many({"user_id": user_id})
        return res.deleted_count

    async def update_action_status_in_chat(
        self,
        action_id: str,
        new_status: str,
        card_url: Optional[str] = None,
        card_id: Optional[str] = None,
        execution_result: Optional[Dict[str, Any]] = None,
        updated_draft: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Updates chat message preview state so UI remains synchronized after approvals."""
        updates: Dict[str, Any] = {
            "approval_preview.status": new_status,
            "execution_status": new_status,
        }
        if card_url:
            updates["approval_preview.card_url"] = card_url
            updates["approval_preview.cardUrl"] = card_url
        if card_id:
            updates["approval_preview.card_id"] = card_id
            updates["approval_preview.cardId"] = card_id
        if execution_result:
            updates["execution_result"] = execution_result
            updates["approval_preview.execution_result"] = execution_result
            updates["approval_preview.executionResult"] = execution_result
        if updated_draft:
            updates["approval_preview.draft"] = updated_draft
            updates["approval_preview.card_name"] = updated_draft.get("title")
            updates["approval_preview.cardName"] = updated_draft.get("title")

        res = await self.collection.update_many(
            {
                "$or": [
                    {"action_id": action_id},
                    {"approval_preview.action_id": action_id},
                    {"approval_preview.actionId": action_id},
                ]
            },
            {"$set": updates},
        )
        return res.modified_count > 0

