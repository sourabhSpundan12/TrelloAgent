from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase


class ToolRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db["tools"]

    async def create(self, tool_doc: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a new tool record."""
        now = datetime.now(timezone.utc)
        tool_doc["created_at"] = tool_doc.get("created_at") or now
        tool_doc["updated_at"] = now
        await self.collection.insert_one(tool_doc)
        tool_doc.pop("_id", None)
        return tool_doc

    async def get_by_tool_id(self, tool_id: str) -> Optional[Dict[str, Any]]:
        """Find a tool by unique tool_id."""
        doc = await self.collection.find_one({"tool_id": tool_id})
        if doc:
            doc.pop("_id", None)
        return doc

    get_by_id = get_by_tool_id

    async def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Find a tool by unique human-readable name."""
        doc = await self.collection.find_one({"name": name})
        if doc:
            doc.pop("_id", None)
        return doc

    async def update(self, tool_id: str, update_doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update fields of an existing tool."""
        update_doc["updated_at"] = datetime.now(timezone.utc)
        result = await self.collection.find_one_and_update(
            {"tool_id": tool_id},
            {"$set": update_doc},
            return_document=True,
        )
        if result:
            result.pop("_id", None)
        return result

    async def set_enabled(self, tool_id: str, enabled: bool) -> Optional[Dict[str, Any]]:
        """Enable or disable a tool."""
        return await self.update(tool_id, {"enabled": enabled})

    async def delete(self, tool_id: str) -> bool:
        """Delete a tool by tool_id."""
        result = await self.collection.delete_one({"tool_id": tool_id})
        return result.deleted_count > 0

    async def list_tools(
        self,
        skip: int = 0,
        limit: int = 50,
        category: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List tools with filtering and pagination."""
        filter_query: Dict[str, Any] = {}
        if category:
            filter_query["category"] = category
        if enabled is not None:
            filter_query["enabled"] = enabled

        total = await self.collection.count_documents(filter_query)
        cursor = self.collection.find(filter_query).skip(skip).limit(limit).sort("created_at", -1)
        tools = []
        async for doc in cursor:
            doc.pop("_id", None)
            tools.append(doc)
        return tools, total

    async def get_active_tools(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve all active (enabled=True) tools for discovery."""
        filter_query: Dict[str, Any] = {"enabled": True}
        if category:
            filter_query["category"] = category
        cursor = self.collection.find(filter_query)
        tools = []
        async for doc in cursor:
            doc.pop("_id", None)
            tools.append(doc)
        return tools

    async def count(self) -> int:
        return await self.collection.count_documents({})

