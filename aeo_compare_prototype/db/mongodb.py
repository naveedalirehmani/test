"""MongoDB connection (defaults to a locally-installed MongoDB)."""

import os

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

# Global MongoDB client
_client: AsyncIOMotorClient | None = None
_database = None


def get_mongodb_client() -> AsyncIOMotorClient:
    """Get or create MongoDB client."""
    global _client
    if _client is None:
        # Defaults to a locally-installed MongoDB; override via env if needed.
        mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        _client = AsyncIOMotorClient(mongodb_uri)
    return _client


def get_database():
    """Get MongoDB database instance."""
    global _database
    if _database is None:
        client = get_mongodb_client()
        db_name = os.getenv("MONGODB_DB_NAME", "zicy_tools")
        _database = client[db_name]
    return _database


def get_collection(collection_name: str) -> AsyncIOMotorCollection:
    """Get a MongoDB collection."""
    database = get_database()
    return database[collection_name]


async def close_mongodb_connection():
    """Close MongoDB connection."""
    global _client, _database
    if _client is not None:
        _client.close()
        _client = None
        _database = None

