from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument


class ApprovalRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db["pending_actions"]

    async def create(self, action_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Inserts a new pending action record into MongoDB."""
        action_dict["created_at"] = action_dict.get("created_at") or datetime.now(timezone.utc)
        action_dict["updated_at"] = datetime.now(timezone.utc)
        await self.collection.insert_one(action_dict)
        return action_dict

    async def get_by_action_id(self, action_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a pending action document by its unique action_id slug."""
        return await self.collection.find_one({"action_id": action_id})

    async def update(self, action_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Updates arbitrary fields on the pending action document."""
        updates["updated_at"] = datetime.now(timezone.utc)
        return await self.collection.find_one_and_update(
            {"action_id": action_id},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )

    async def transition_status_atomically(
        self,
        action_id: str,
        from_status: str,
        to_status: str,
        extra_updates: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Atomically transitions an action from one status to another.
        Prevents race conditions and duplicate double-click executions.
        Returns None if document does not exist or was not in from_status.
        """
        set_payload = {
            "status": to_status,
            "updated_at": datetime.now(timezone.utc),
        }
        if extra_updates:
            set_payload.update(extra_updates)

        return await self.collection.find_one_and_update(
            {"action_id": action_id, "status": from_status},
            {"$set": set_payload},
            return_document=ReturnDocument.AFTER,
        )

    async def list_by_user(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Lists pending actions initiated by a specific user."""
        cursor = self.collection.find({"user_id": user_id}).sort("created_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

