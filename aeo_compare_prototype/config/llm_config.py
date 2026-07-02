"""LLM configuration - initialize LLM clients.

All AI response fetching is routed through DataForSEO APIs.
OpenAI (instructor) is used only for parsing raw responses into structured data.
"""

import base64
import os
from dataclasses import dataclass

import instructor
from openai import OpenAI


@dataclass
class LLMResponse:
    """Response from an LLM provider with cost tracking."""

    text: str | None
    tokens_input: int
    tokens_output: int
    model: str
    provider: str
    cost_usd: float


# All providers now use DataForSEO fixed pricing per request.
# OpenAI (gpt-5-mini) is used only for parsing, not response fetching.
LLM_PRICING = {
    "gpt-5-mini": {
        "input": float(os.getenv("PRICE_GPT5_MINI_INPUT", "1.10")),
        "output": float(os.getenv("PRICE_GPT5_MINI_OUTPUT", "4.40")),
    },
    "dataforseo": {
        "per_request": float(os.getenv("PRICE_DATAFORSEO_REQUEST", "0.01")),
    },
}


def calculate_cost(model: str, tokens_input: int, tokens_output: int) -> float:
    """Calculate cost in USD based on token usage."""
    pricing = LLM_PRICING.get(model)
    if not pricing:
        return 0.0

    if "per_request" in pricing:
        return pricing["per_request"]

    input_cost = (tokens_input / 1_000_000) * pricing.get("input", 0)
    output_cost = (tokens_output / 1_000_000) * pricing.get("output", 0)
    return input_cost + output_cost


class DataForSEOClient:
    """DataForSEO client used by all providers for fetching AI responses."""

    def __init__(self, login: str, password: str):
        self.login = login
        self.password = password
        self.base_url = os.getenv("DATAFORSEO_BASE_URL", "https://api.dataforseo.com/v3").rstrip("/")

    def get_auth_header(self) -> dict[str, str]:
        """Generate authentication header for DataForSEO API."""
        token = base64.b64encode(f"{self.login}:{self.password}".encode()).decode()
        return {"Authorization": f"Basic {token}"}


class LLMConfig:
    """Configuration class for LLM clients."""

    _openai_client = None
    _dataforseo_client = None

    @classmethod
    def get_openai_client(cls):
        """Get or initialize OpenAI client (used for parsing only)."""
        if cls._openai_client is None:
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if openai_api_key:
                cls._openai_client = instructor.from_openai(
                    OpenAI(api_key=openai_api_key)
                )
        return cls._openai_client

    @classmethod
    def get_dataforseo_client(cls):
        """Get or initialize DataForSEO client (used by all providers)."""
        if cls._dataforseo_client is None:
            login = os.getenv("DATAFORSEO_LOGIN")
            password = os.getenv("DATAFORSEO_PASSWORD")
            if login and password:
                cls._dataforseo_client = DataForSEOClient(login, password)
        return cls._dataforseo_client

