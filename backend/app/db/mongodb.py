# Re-exporting from app.database.mongodb for backwards compatibility
from app.database.mongodb import MongoDBManager, get_database, get_db

__all__ = ["MongoDBManager", "get_database", "get_db"]
