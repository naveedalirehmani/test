"""Instructor service - parse LLM responses using instructor.

MIRRORS zicy-tools per-provider parsing logic to ensure consistency.
Each provider is parsed individually (no batching) for better accuracy
and consistency with the initial analysis flow.
"""

import asyncio

from pydantic import ValidationError

from config.llm_config import LLMConfig
from models.llm_model import AEOResponseAnalysisSchema
from prompts.aeo_prompts import build_provider_parsing_prompt


class InstructorService:
    """Service for parsing LLM responses using instructor (per-provider parsing)."""

    @staticmethod
    async def parse_provider_response(
        provider: str,
        raw_response: str,
        target_brand_names: list[str],
        business_profile: dict,
    ) -> AEOResponseAnalysisSchema:
        """
        Parse a single provider's response using instructor.

        This mirrors zicy-tools AEOAnalysisService._parse_response_with_instructor
        to ensure consistency between initial analysis and re-analysis.

        Uses per-provider parsing with business_profile context for accurate
        brand extraction, competitor filtering, and multi-dimensional sentiment.

        Args:
            provider: Provider name (e.g., "chatgpt", "gemini")
            raw_response: The raw LLM response text to parse
            target_brand_names: List of target brand names
            business_profile: Full business profile dict for context

        Returns:
            AEOResponseAnalysisSchema with parsed analysis

        Raises:
            Exception: If parsing fails after retry
        """
        try:
            client = LLMConfig.get_openai_client()
            if not client:
                raise Exception("OpenAI client not initialized - required for parsing")

            if not raw_response:
                raise Exception("No response to parse")

            # Build parsing prompt using template function with business context
            # MIRRORS zicy-tools build_provider_parsing_prompt exactly
            parsing_prompt = build_provider_parsing_prompt(
                provider, raw_response, target_brand_names, business_profile
            )

            # Use instructor to get structured output.
            # Parsing: do not send temperature params (deterministic extraction).
            parsed = await asyncio.to_thread(
                client.chat.completions.create,
                model="gpt-5-mini",
                response_model=AEOResponseAnalysisSchema,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at analyzing text and extracting structured information about brand mentions, citations, and positioning.",
                    },
                    {"role": "user", "content": parsing_prompt},
                ],
            )

            return parsed

        except ValidationError as e:
            raise Exception(
                f"Failed to parse {provider} response with instructor: {str(e)}"
            ) from e
        except Exception as e:
            raise Exception(f"Error during {provider} instructor parsing: {str(e)}") from e
