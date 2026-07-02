"""Local-DB storage for comparison sessions (prototype).

Uses the same local MongoDB as the rest of the platform (via MONGODB_URI) but
writes only to its own collection, ``aeo_compare_sessions``, so nothing
existing is touched. Sessions use a string UUID ``_id`` to keep JSON simple.
"""

import os
import uuid
from datetime import UTC, datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

SESSIONS_COLLECTION = "aeo_compare_sessions"

_client: AsyncIOMotorClient | None = None


def _db():
    global _client
    if _client is None:
        # Defaults to a locally-installed MongoDB; override via env if needed.
        uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        _client = AsyncIOMotorClient(uri)
    return _client[os.getenv("MONGODB_DB_NAME", "zicy_tools")]


def _coll():
    return _db()[SESSIONS_COLLECTION]


async def create_session(session: dict) -> dict:
    """Insert a new session. Adds _id (uuid) and created_at."""
    doc = dict(session)
    doc["_id"] = uuid.uuid4().hex
    doc["created_at"] = datetime.now(UTC)
    await _coll().insert_one(doc)
    return _jsonable(doc)


async def list_sessions(limit: int = 50) -> list[dict]:
    """Return lightweight session summaries, newest first."""
    cursor = _coll().find(
        {},
        {
            "_id": 1,
            "created_at": 1,
            "business_name": 1,
            "providers": 1,
            "prompts.prompt_text": 1,
            "reparse_of": 1,
        },
    ).sort("created_at", -1).limit(limit)
    out = []
    async for doc in cursor:
        out.append(
            {
                "id": doc["_id"],
                "created_at": _iso(doc.get("created_at")),
                "business_name": doc.get("business_name"),
                "providers": doc.get("providers", []),
                "prompt_count": len(doc.get("prompts", [])),
                "reparse_of": doc.get("reparse_of"),
            }
        )
    return out


async def get_session(session_id: str) -> dict | None:
    doc = await _coll().find_one({"_id": session_id})
    return _jsonable(doc) if doc else None


def _iso(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _to_jsonable(v):
    """Recursively convert ObjectId/datetime to JSON-safe values."""
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: _to_jsonable(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_to_jsonable(x) for x in v]
    return v


def _jsonable(doc: dict) -> dict:
    """Deep-normalize a session doc for JSON responses (handles nested ObjectId/datetime)."""
    out = _to_jsonable(doc)
    if "_id" in out:
        out["id"] = out.pop("_id")
    return out


async def close():
    global _client
    if _client is not None:
        _client.close()
        _client = None
