"""Provider configurations for AEO analysis service.

NOTE: This file is a MIRROR of zicy-tools provider configuration to ensure consistency.
Any changes to provider models should be synchronized between both codebases.

All providers route through DataForSEO APIs for fetching AI responses.
"""

import os


def get_provider_configs():
    """
    Get provider configurations for AEO analysis.

    All providers use DataForSEO as the intermediary:
    - chatgpt: DataForSEO ChatGPT LLM Scraper
    - gemini: DataForSEO Gemini LLM Scraper
    - perplexity: DataForSEO Perplexity LLM Responses
    - google_ai_mode: DataForSEO SERP Google AI Mode
    - ai_overview: DataForSEO SERP Google Organic (async AI Overview)

    Returns:
        dict: Provider configurations with model information
    """
    return {
        "chatgpt": {
            "model": "gpt-5-2",
        },
        "gemini": {
            "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        },
        "perplexity": {
            "model": os.getenv("PERPLEXITY_MODEL", "sonar-reasoning"),
        },
        "google_ai_mode": {
            "model": "google-ai-mode",
        },
        "ai_overview": {
            "model": "ai-overview",
        },
    }


def get_provider_model(provider: str) -> str:
    """
    Get the model name for a specific provider.

    Args:
        provider: Provider name (e.g., "chatgpt", "gemini")

    Returns:
        Model name string, or None if provider not found
    """
    configs = get_provider_configs()
    if provider in configs:
        return configs[provider]["model"]
    return None


def get_all_provider_names() -> list[str]:
    """
    Get list of all configured provider names.

    Returns:
        List of provider names (e.g., ["chatgpt", "gemini", ...])
    """
    return list(get_provider_configs().keys())

