from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.models.user import UserRole


class UserRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db["users"]

    async def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Find a user by string or ObjectId."""
        query = {"_id": ObjectId(user_id)} if ObjectId.is_valid(user_id) else {"_id": user_id}
        doc = await self.collection.find_one(query)
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Find a user by normalized lowercase email."""
        doc = await self.collection.find_one({"email": email.strip().lower()})
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def create(self, user_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a new user document."""
        user_dict["email"] = user_dict["email"].strip().lower()
        now = datetime.now(timezone.utc)
        user_dict["created_at"] = now
        user_dict["updated_at"] = now

        result = await self.collection.insert_one(user_dict)
        user_dict["id"] = str(result.inserted_id)
        if "_id" in user_dict:
            del user_dict["_id"]
        return user_dict

    async def update(self, user_id: str, update_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update user fields."""
        query = {"_id": ObjectId(user_id)} if ObjectId.is_valid(user_id) else {"_id": user_id}
        update_dict["updated_at"] = datetime.now(timezone.utc)

        await self.collection.update_one(query, {"$set": update_dict})
        return await self.get_by_id(user_id)

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 50,
        role: Optional[UserRole] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List users with pagination and optional role filter."""
        query: Dict[str, Any] = {}
        if role:
            query["role"] = role.value if hasattr(role, "value") else str(role)

        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)

        users = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            users.append(doc)
        return users, total

    async def count_users(self) -> int:
        return await self.collection.count_documents({})


class RefreshTokenRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db["refresh_tokens"]

    async def create(self, token_data: Dict[str, Any]) -> None:
        """Store hashed refresh token."""
        await self.collection.insert_one(token_data)

    async def get_by_hash(self, token_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieve token record by hash."""
        return await self.collection.find_one({"token_hash": token_hash})

    async def revoke(self, token_hash: str) -> bool:
        """Mark token as revoked."""
        res = await self.collection.update_one(
            {"token_hash": token_hash},
            {"$set": {"is_revoked": True}},
        )
        return res.modified_count > 0

    async def delete(self, token_hash: str) -> bool:
        """Remove a refresh token record."""
        res = await self.collection.delete_one({"token_hash": token_hash})
        return res.deleted_count > 0

    async def revoke_all_for_user(self, user_id: str) -> int:
        """Revoke all tokens for a user (e.g. password change)."""
        res = await self.collection.update_many(
            {"user_id": user_id},
            {"$set": {"is_revoked": True}},
        )
        return res.modified_count


class PasswordResetRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db["password_resets"]

    async def create_reset_code(self, email: str, code: str, expires_at: datetime) -> None:
        """Invalidates older active codes for this email and stores a fresh code."""
        normalized = email.strip().lower()
        now = datetime.now(timezone.utc)
        await self.collection.update_many(
            {"email": normalized, "is_used": False},
            {"$set": {"is_used": True, "invalidated_at": now}},
        )
        await self.collection.insert_one({
            "email": normalized,
            "code": code.strip(),
            "expires_at": expires_at,
            "is_used": False,
            "created_at": now,
        })

    async def verify_code(self, email: str, code: str) -> bool:
        """Verifies if code exists, is unused, and has not expired."""
        normalized = email.strip().lower()
        now = datetime.now(timezone.utc)
        record = await self.collection.find_one({
            "email": normalized,
            "code": code.strip(),
            "is_used": False,
            "expires_at": {"$gt": now},
        })
        return record is not None

    async def mark_used(self, email: str, code: str) -> None:
        """Marks reset code as consumed."""
        normalized = email.strip().lower()
        await self.collection.update_one(
            {"email": normalized, "code": code.strip()},
            {"$set": {"is_used": True, "used_at": datetime.now(timezone.utc)}},
        )


