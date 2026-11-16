from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase


class MCPServerRepository:
    """MongoDB repository for configured MCP servers."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db["mcp_servers"]

    async def create(self, server_doc: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        server_doc["created_at"] = server_doc.get("created_at") or now
        server_doc["updated_at"] = now
        server_doc.setdefault("status", "DISCONNECTED")
        server_doc.setdefault("discovered_tool_count", 0)
        await self.collection.insert_one(server_doc)
        server_doc.pop("_id", None)
        return server_doc

    async def get_by_server_id(self, server_id: str) -> Optional[Dict[str, Any]]:
        doc = await self.collection.find_one({"server_id": server_id})
        if doc:
            doc.pop("_id", None)
        return doc

    async def update(self, server_id: str, update_doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        update_doc["updated_at"] = datetime.now(timezone.utc)
        result = await self.collection.find_one_and_update(
            {"server_id": server_id},
            {"$set": update_doc},
            return_document=True,
        )
        if result:
            result.pop("_id", None)
        return result

    async def delete(self, server_id: str) -> bool:
        result = await self.collection.delete_one({"server_id": server_id})
        return result.deleted_count > 0

    async def list_servers(
        self,
        skip: int = 0,
        limit: int = 50,
        enabled: Optional[bool] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        filter_query: Dict[str, Any] = {}
        if enabled is not None:
            filter_query["enabled"] = enabled

        total = await self.collection.count_documents(filter_query)
        cursor = self.collection.find(filter_query).skip(skip).limit(limit).sort("created_at", -1)
        servers = []
        async for doc in cursor:
            doc.pop("_id", None)
            servers.append(doc)
        return servers, total

    async def count(self) -> int:
        return await self.collection.count_documents({})

