"""
Database Migration Script: Local MongoDB -> MongoDB Atlas
Agentic Task Manager
Safe, non-destructive migration preserving existing local data.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_path = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(backend_path))

from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.core.logging import logger
from app.database.indexes import create_database_indexes
from app.database.mongodb import mask_mongo_uri


async def migrate_data():
    local_uri = "mongodb://localhost:27017"
    atlas_uri = settings.EFFECTIVE_MONGODB_URI
    db_name = settings.MONGODB_DATABASE

    print(f"[*] Local Source URI : {mask_mongo_uri(local_uri)}")
    print(f"[*] Atlas Target URI : {mask_mongo_uri(atlas_uri)}")
    print(f"[*] Database Name    : {db_name}")

    if not atlas_uri.startswith("mongodb+srv://") and "mongodb.net" not in atlas_uri:
        print("[!] Target URI does not appear to be MongoDB Atlas. Aborting to avoid unintended writes.")
        return False

    print("\n--- Step 1: Connecting to Local MongoDB and MongoDB Atlas ---")
    local_client = AsyncIOMotorClient(local_uri, serverSelectionTimeoutMS=5000)
    atlas_client = AsyncIOMotorClient(atlas_uri, serverSelectionTimeoutMS=10000)

    try:
        await local_client.admin.command("ping")
        print("  [OK] Local MongoDB ping successful.")
    except Exception as e:
        print(f"  [FAIL] Failed to connect to local MongoDB: {e}")
        return False

    try:
        await atlas_client.admin.command("ping")
        print("  [OK] MongoDB Atlas ping successful.")
    except Exception as e:
        print(f"  [FAIL] Failed to connect to MongoDB Atlas: {e}")
        return False

    local_db = local_client[db_name]
    atlas_db = atlas_client[db_name]

    print("\n--- Step 2: Ensuring Indexes on MongoDB Atlas ---")
    await create_database_indexes(atlas_db)
    print("  [OK] Created required indexes on MongoDB Atlas.")

    print("\n--- Step 3: Copying Collections (Preserving Local Data) ---")
    collections_to_migrate = [
        "users",
        "tools",
        "refresh_tokens",
        "pending_actions",
        "mcp_servers",
        "audit_logs",
        "employee_snapshots",
        "task_activities",
    ]

    for col_name in collections_to_migrate:
        local_col = local_db[col_name]
        atlas_col = atlas_db[col_name]

        local_count = await local_col.count_documents({})
        atlas_count_before = await atlas_col.count_documents({})
        print(f"\nProcessing '{col_name}': local count = {local_count}, atlas count before = {atlas_count_before}")

        if local_count == 0:
            print(f"  [INFO] Collection '{col_name}' has 0 local documents. Skipping data copy.")
            continue

        migrated_count = 0
        skipped_count = 0
        cursor = local_col.find({})
        async for doc in cursor:
            # Check for existing document by unique keys to prevent duplicate key errors
            unique_query = {"_id": doc["_id"]}
            if col_name == "users" and "email" in doc:
                unique_query = {"$or": [{"_id": doc["_id"]}, {"email": doc["email"]}]}
            elif col_name == "tools":
                candidates = [{"_id": doc["_id"]}]
                if "tool_id" in doc:
                    candidates.append({"tool_id": doc["tool_id"]})
                if "name" in doc:
                    candidates.append({"name": doc["name"]})
                unique_query = {"$or": candidates}
            elif col_name == "pending_actions" and "action_id" in doc:
                unique_query = {"$or": [{"_id": doc["_id"]}, {"action_id": doc["action_id"]}]}
            elif col_name == "refresh_tokens" and "token_hash" in doc:
                unique_query = {"$or": [{"_id": doc["_id"]}, {"token_hash": doc["token_hash"]}]}
            elif col_name == "mcp_servers" and "server_id" in doc:
                unique_query = {"$or": [{"_id": doc["_id"]}, {"server_id": doc["server_id"]}]}

            existing = await atlas_col.find_one(unique_query)
            if existing is None:
                await atlas_col.insert_one(doc)
                migrated_count += 1
            else:
                skipped_count += 1

        atlas_count_after = await atlas_col.count_documents({})
        print(f"  [DONE] '{col_name}': inserted {migrated_count}, already existing {skipped_count}, total on Atlas = {atlas_count_after}")

    print("\n--- Step 4: Verification of Collections and Indexes on Atlas ---")
    atlas_collections = await atlas_db.list_collection_names()
    print(f"Atlas Collections: {atlas_collections}")
    for col in atlas_collections:
        count = await atlas_db[col].count_documents({})
        indexes = await atlas_db[col].index_information()
        idx_names = list(indexes.keys())
        print(f"  * {col}: {count} documents, indexes={idx_names}")

    print("\n[SUCCESS] Local MongoDB -> MongoDB Atlas Migration Complete!")
    local_client.close()
    atlas_client.close()
    return True


if __name__ == "__main__":
    success = asyncio.run(migrate_data())
    sys.exit(0 if success else 1)
