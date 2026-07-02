"""Business repository - database operations for business profiles."""

import logging

from bson import ObjectId

from db.mongodb import get_collection
from db.collection_model import CollectionEnum

logger = logging.getLogger(__name__)


async def get_business_profile(user_id: str, business_id: str) -> dict | None:
    """Get a business profile by user and business ID.

    Security: Always validates both user_id and business_id to prevent
    cross-user data access.

    Note: business_id can be either:
    - A MongoDB ObjectId string (24-char hex) - query by _id
    - A prefixed string like 'biz_xxx' - query by business_id field
    """
    collection = get_collection(CollectionEnum.BUSINESS_PROFILES.value)

    # Check if business_id is a valid ObjectId (24-char hex string)
    if len(business_id) == 24 and all(c in '0123456789abcdefABCDEF' for c in business_id):
        # Query by _id (as ObjectId)
        query = {"_id": ObjectId(business_id), "owner_user_id": user_id}
    else:
        # Query by business_id field (for prefixed IDs like 'biz_xxx')
        query = {"business_id": business_id, "owner_user_id": user_id}

    return await collection.find_one(query)


async def get_business_by_id(business_id: str) -> dict | None:
    """Get a business profile by ID only (no user_id validation).

    Used by cron jobs where we only have the business_id from the prompt.

    Args:
        business_id: The business ID (either ObjectId string or prefixed ID)

    Returns:
        The business profile document or None if not found
    """
    collection = get_collection(CollectionEnum.BUSINESS_PROFILES.value)

    # Check if business_id is a valid ObjectId (24-char hex string)
    if len(business_id) == 24 and all(c in '0123456789abcdefABCDEF' for c in business_id):
        # Query by _id (as ObjectId)
        return await collection.find_one({"_id": ObjectId(business_id)})
    else:
        # Query by business_id field (for prefixed IDs like 'biz_xxx')
        return await collection.find_one({"business_id": business_id})


async def get_pitch_mode_business_ids() -> set[str]:
    """Return identifiers of all businesses currently in pitch_mode.

    Prompts may reference a business by either the ObjectId hex string of
    `_id` or the prefixed `business_id` field. Both forms are returned so
    callers can filter prompts regardless of which format was stored.

    Returns:
        Set of identifier strings (mix of ObjectId hex strings and prefixed
        business_id values).
    """
    collection = get_collection(CollectionEnum.BUSINESS_PROFILES.value)
    cursor = collection.find(
        {"pitch_mode": True},
        {"_id": 1, "business_id": 1},
    )
    ids: set[str] = set()
    async for doc in cursor:
        ids.add(str(doc["_id"]))
        prefixed = doc.get("business_id")
        if prefixed:
            ids.add(prefixed)
    return ids


async def get_brand_names_for_business(user_id: str, business_id: str) -> list[str]:
    """Get all brand names for a business profile."""
    business_profile = await get_business_profile(user_id, business_id)

    if not business_profile:
        return []

    brand_names = []

    # Add business_name first (primary brand)
    if business_profile.get("business_name"):
        brand_names.append(business_profile["business_name"])

    # Add all brand name variations
    if business_profile.get("brand_names"):
        for brand_name in business_profile["brand_names"]:
            if brand_name and brand_name not in brand_names:
                brand_names.append(brand_name)

    # Fallback
    if not brand_names:
        brand_names = ["Your Brand"]

    return brand_names
