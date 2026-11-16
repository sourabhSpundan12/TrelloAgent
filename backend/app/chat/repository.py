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
                    "title": title,
                    "created_at": now,
                    "updated_at": now,
                    "message_count": 1,
                })
            else:
                update_fields: Dict[str, Any] = {
                    "updated_at": now,
                }
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

    async def list_sessions(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves conversation sessions for a user in reverse chronological order."""
        cursor = self.sessions_collection.find({"user_id": user_id}).sort("updated_at", -1).limit(limit)
        sessions = []
        async for doc in cursor:
            doc.pop("_id", None)
            sessions.append(doc)

        # Backward compatibility: if no explicit sessions exist yet but user has messages
        if not sessions:
            legacy_count = await self.collection.count_documents({"user_id": user_id})
            if legacy_count > 0:
                first_user_msg = await self.collection.find_one({"user_id": user_id, "sender": "user"})
                raw_title = first_user_msg.get("content", "General Chat") if first_user_msg else "General Chat"
                title = re.sub(r"\s+", " ", str(raw_title))[:45]
                default_session_id = "SES-DEFAULT"
                now = datetime.now(timezone.utc)
                await self.collection.update_many(
                    {"user_id": user_id, "conversation_id": {"$exists": False}},
                    {"$set": {"conversation_id": default_session_id}},
                )
                session_doc = {
                    "id": default_session_id,
                    "user_id": user_id,
                    "title": title,
                    "created_at": now,
                    "updated_at": now,
                    "message_count": legacy_count,
                }
                await self.sessions_collection.insert_one(dict(session_doc))
                session_doc.pop("_id", None)
                sessions.append(session_doc)

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

