import asyncio
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.core.config import settings
from app.core.logging import logger
from app.core.exceptions import DatabaseConnectionError
from app.database.indexes import create_database_indexes


import asyncio
import re
from typing import Any, Dict, Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import (
    ConfigurationError,
    ConnectionFailure,
    OperationFailure,
    ServerSelectionTimeoutError,
)
from app.core.config import settings
from app.core.logging import logger
from app.core.exceptions import DatabaseConnectionError
from app.database.indexes import create_database_indexes


def mask_mongo_uri(uri: str) -> str:
    """
    Mask credentials in MongoDB connection string for safe logging.
    Preserves hostname, cluster, replica set, and database name.
    """
    if not uri:
        return ""
    # Matches ://username:password@ or ://password@
    return re.sub(r"://([^:@]+):([^@]+)@", r"://\1:****@", uri)


class MongoDBManager:
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None

    @classmethod
    async def connect(cls) -> bool:
        """Initialize MongoDB client, verify connection with ping, and create indexes."""
        raw_uri = settings.EFFECTIVE_MONGODB_URI
        masked = mask_mongo_uri(raw_uri)
        is_atlas = raw_uri.startswith("mongodb+srv://")

        try:
            target_type = "MongoDB Atlas" if is_atlas else "Local/Standalone MongoDB"
            logger.info(f"Connecting to {target_type} at {masked} (DB: {settings.MONGODB_DATABASE})...")

            cls.client = AsyncIOMotorClient(
                raw_uri,
                minPoolSize=settings.MONGODB_MIN_POOL_SIZE,
                maxPoolSize=settings.MONGODB_MAX_POOL_SIZE,
                serverSelectionTimeoutMS=settings.MONGODB_TIMEOUT_MS,
                retryWrites=True,
            )
            cls.db = cls.client[settings.MONGODB_DATABASE]

            # Verify connectivity via ping
            await cls.client.admin.command("ping")
            logger.info(f"Successfully connected to {target_type} ({masked}).")

            # Ensure required indexes
            await create_database_indexes(cls.db)
            return True

        except ServerSelectionTimeoutError as sste:
            logger.error(
                f"Failed to connect to MongoDB ({masked}): Server selection timed out after "
                f"{settings.MONGODB_TIMEOUT_MS}ms. Check network connectivity, DNS/IP whitelist, or cluster status. Details: {sste}"
            )
            return False
        except ConfigurationError as ce:
            logger.error(f"MongoDB configuration error ({masked}): {ce}")
            return False
        except OperationFailure as ofe:
            logger.error(f"MongoDB authentication/operation error ({masked}): code={ofe.code}, message={ofe.details}")
            return False
        except ConnectionFailure as cf:
            logger.error(f"MongoDB connection failure ({masked}): {cf}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error connecting to MongoDB ({masked}): {type(e).__name__}: {e}")
            return False

    @classmethod
    async def disconnect(cls):
        """Close MongoDB connection pool gracefully."""
        if cls.client is not None:
            logger.info("Closing MongoDB connection pool...")
            cls.client.close()
            cls.client = None
            cls.db = None
            logger.info("MongoDB connection pool closed.")

    @classmethod
    async def ping(cls) -> bool:
        """Perform a quick ping command to verify database availability."""
        if cls.client is None or cls.db is None:
            return False
        try:
            await asyncio.wait_for(
                cls.client.admin.command("ping"),
                timeout=settings.MONGODB_TIMEOUT_MS / 1000.0,
            )
            return True
        except Exception:
            return False

    @classmethod
    async def get_health_status(cls) -> Dict[str, Any]:
        """Detailed status for readiness/health probes."""
        is_alive = await cls.ping()
        masked = mask_mongo_uri(settings.EFFECTIVE_MONGODB_URI)
        is_atlas = settings.EFFECTIVE_MONGODB_URI.startswith("mongodb+srv://")
        return {
            "connected": is_alive,
            "type": "atlas" if is_atlas else "standalone",
            "database": settings.MONGODB_DATABASE,
            "uri": masked,
        }

    @classmethod
    async def ensure_indexes(cls):
        """Ensure all required database indexes are created."""
        if cls.db is not None:
            await create_database_indexes(cls.db)

    @classmethod
    def get_db(cls) -> AsyncIOMotorDatabase:
        if cls.db is None:
            raise DatabaseConnectionError("Database connection has not been initialized.")
        return cls.db


async def get_database() -> AsyncIOMotorDatabase:
    """FastAPI Dependency for obtaining the MongoDB database."""
    return MongoDBManager.get_db()


# Alias for dependency consistency
get_db = get_database
