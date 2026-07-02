"""Collection model - Enum for MongoDB collection names."""

from enum import Enum


class CollectionEnum(str, Enum):
    """MongoDB collection names."""

    AEO_PROMPT_SUGGESTIONS = "aeo_prompt_suggestions"
    AEO_ANALYSIS_RESULTS = "aeo_analysis_results"
    AEO_CITATIONS = "aeo_citations"
    BUSINESS_PROFILES = "business_profiles"
    ADMIN_REANALYSIS_QUEUE = "admin_reanalysis_queue"
    # Quota-related collections
    USERS = "users"
    USER_QUOTAS = "user_quotas"
    ORG_QUOTAS = "org_quotas"
    STRIPE_SUBSCRIPTIONS = "stripe_subscriptions"

