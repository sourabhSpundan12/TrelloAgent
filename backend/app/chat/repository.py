from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase


class ChatRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db["chat_messages"]

    async def add_message(self, message_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Saves a chat message to MongoDB Atlas."""
        message_dict.setdefault("created_at", datetime.now(timezone.utc))
        await self.collection.insert_one(message_dict)
        message_dict.pop("_id", None)
        return message_dict

    async def get_history(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieves user conversation history in chronological order."""
        cursor = self.collection.find({"user_id": user_id}).sort("created_at", 1).limit(limit)
        messages = []
        async for doc in cursor:
            doc.pop("_id", None)
            messages.append(doc)
        return messages

    async def clear_history(self, user_id: str) -> int:
        """Clears all conversation history for a user."""
        res = await self.collection.delete_many({"user_id": user_id})
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

