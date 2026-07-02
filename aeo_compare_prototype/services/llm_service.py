"""LLM service - interact with LLM providers via DataForSEO APIs.

MIRRORS zicy-tools AEOAnalysisService._get_llm_response() to ensure consistency
between initial analysis and re-analysis.

All AI response fetching is routed through DataForSEO APIs.
"""

import asyncio
import logging
import os
import re
import time

import httpx

from config.llm_config import LLMConfig, LLMResponse, calculate_cost
from utils.url_filters import should_filter_url

logger = logging.getLogger(__name__)


def _embed_dataforseo_perplexity_citations(
    content: str, annotations: list[dict]
) -> str:
    """Embed DataForSEO Perplexity citation annotations as inline markdown links.

    DataForSEO returns annotations as [{title, url}, ...] in section objects.
    We append them as a numbered reference list at the end of the content
    and embed inline links for any matching citation markers like [1], [2].
    """
    if not annotations:
        return content

    ref_lines = []
    for i, ann in enumerate(annotations, 1):
        url = ann.get("url", "")
        title = ann.get("title", url)
        if url:
            ref_lines.append(f"[{i}] [{title}]({url})")

    def replace_citation(match: re.Match) -> str:
        num = int(match.group(1))
        if 1 <= num <= len(annotations):
            url = annotations[num - 1].get("url", "")
            if url:
                return f"[[{num}]]({url})"
        return match.group(0)

    content = re.sub(r"\[(\d+)\]", replace_citation, content)

    if ref_lines:
        content += "\n\n---\nSources:\n" + "\n".join(ref_lines)

    return content


class LLMService:
    """Service for interacting with LLM providers via DataForSEO."""

    @staticmethod
    async def get_llm_response(prompt_text: str, provider: str, model: str) -> LLMResponse:
        """Get raw, unbiased response from LLM via DataForSEO APIs."""
        client = LLMConfig.get_dataforseo_client()
        if not client:
            raise Exception("DataForSEO client not initialized")

        headers = client.get_auth_header()
        base_url = client.base_url

        try:
            if provider == "chatgpt":
                endpoint = f"{base_url}/ai_optimization/chat_gpt/llm_scraper/live/advanced"
                payload = [
                    {
                        "language_code": "en",
                        "location_code": 2840,
                        "keyword": prompt_text,
                        "force_web_search": True,
                        "tag": "aeo-analysis-chatgpt",
                    }
                ]

                async with httpx.AsyncClient(timeout=60.0) as http_client:
                    response = await http_client.post(
                        endpoint, json=payload, headers=headers
                    )
                    response.raise_for_status()
                    data = response.json()

                markdown_text = _extract_llm_scraper_markdown(data, "chat_gpt_text")
                cost = calculate_cost("dataforseo", 0, 0)

                return LLMResponse(
                    text=markdown_text if markdown_text else "",
                    tokens_input=0,
                    tokens_output=0,
                    model=model,
                    provider=provider,
                    cost_usd=cost,
                )

            elif provider == "gemini":
                endpoint = f"{base_url}/ai_optimization/gemini/llm_scraper/live/advanced"
                payload = [
                    {
                        "language_code": "en",
                        "location_code": 2840,
                        "keyword": prompt_text,
                        "tag": "aeo-analysis-gemini",
                    }
                ]

                async with httpx.AsyncClient(timeout=120.0) as http_client:
                    response = await http_client.post(
                        endpoint, json=payload, headers=headers
                    )
                    response.raise_for_status()
                    data = response.json()

                markdown_text = _extract_llm_scraper_markdown(data, "gemini_text")
                cost = calculate_cost("dataforseo", 0, 0)

                return LLMResponse(
                    text=markdown_text if markdown_text else "",
                    tokens_input=0,
                    tokens_output=0,
                    model=model,
                    provider=provider,
                    cost_usd=cost,
                )

            elif provider == "perplexity":
                endpoint = f"{base_url}/ai_optimization/perplexity/llm_responses/live"
                payload = [
                    {
                        "user_prompt": prompt_text,
                        "model_name": model,
                        "max_output_tokens": 2048,
                        "temperature": 0.7,
                        "web_search_country_iso_code": "US",
                        "tag": "aeo-analysis-perplexity",
                    }
                ]

                async with httpx.AsyncClient(timeout=120.0) as http_client:
                    response = await http_client.post(
                        endpoint, json=payload, headers=headers
                    )
                    response.raise_for_status()
                    data = response.json()

                response_text = _extract_perplexity_response(data)
                cost = calculate_cost("dataforseo", 0, 0)

                return LLMResponse(
                    text=response_text if response_text else "",
                    tokens_input=0,
                    tokens_output=0,
                    model=model,
                    provider=provider,
                    cost_usd=cost,
                )

            elif provider == "google_ai_mode":
                endpoint = f"{base_url}/serp/google/ai_mode/live/advanced"
                payload = [
                    {
                        "keyword": prompt_text,
                        "location_code": 2458,
                        "language_code": "en",
                        "device": "desktop",
                        "os": "windows",
                    }
                ]

                async with httpx.AsyncClient(timeout=30.0) as http_client:
                    response = await http_client.post(
                        endpoint, json=payload, headers=headers
                    )
                    response.raise_for_status()
                    data = response.json()

                markdown_text = _extract_ai_overview_markdown(data)
                cost = calculate_cost("dataforseo", 0, 0)

                return LLMResponse(
                    text=markdown_text if markdown_text else "",
                    tokens_input=0,
                    tokens_output=0,
                    model="dataforseo_ai_mode",
                    provider=provider,
                    cost_usd=cost,
                )

            elif provider == "ai_overview":
                return await LLMService._get_ai_overview_async(
                    prompt_text, model, headers, base_url
                )

            else:
                raise Exception(f"Unsupported provider: {provider}")

        except Exception as e:
            raise Exception(
                f"Failed to get LLM response from {provider}: {str(e)}"
            ) from e

    @staticmethod
    async def _get_ai_overview_async(
        prompt_text: str, model: str, headers: dict, base_url: str
    ) -> LLMResponse:
        """Fetch AI Overview via DataForSEO async task API (submit + poll)."""
        task_post_endpoint = f"{base_url}/serp/google/organic/task_post"
        payload = [
            {
                "language_code": "en",
                "location_code": 2458,
                "keyword": prompt_text,
                "device": "desktop",
                "load_async_ai_overview": True,
                "expand_ai_overview": True,
            }
        ]

        async with httpx.AsyncClient(timeout=30.0) as http_client:
            response = await http_client.post(
                task_post_endpoint, json=payload, headers=headers
            )
            response.raise_for_status()
            task_data = response.json()

        task_id = None
        tasks = task_data.get("tasks", [])
        if tasks:
            task_id = tasks[0].get("id")
        if not task_id:
            raise Exception("Failed to get task ID from DataForSEO response")

        task_get_endpoint = f"{base_url}/serp/google/organic/task_get/advanced/{task_id}"
        max_polling_time = 90
        poll_interval = 3
        start_time = time.time()
        data = None
        task_complete = False

        while time.time() - start_time < max_polling_time:
            async with httpx.AsyncClient(timeout=30.0) as http_client:
                poll_response = await http_client.get(
                    task_get_endpoint, headers=headers
                )
                poll_response.raise_for_status()
                data = poll_response.json()

            poll_tasks = data.get("tasks", [])
            if poll_tasks:
                task = poll_tasks[0]
                status_code = task.get("status_code")
                status_message = task.get("status_message", "")
                result = task.get("result", [])

                if status_code == 20000:
                    if result and len(result) > 0 and result[0].get("items"):
                        task_complete = True
                        break
                elif status_code in [40601, 40602]:
                    logger.info(
                        f"[AI Overview] Task {task_id} is being processed "
                        f"(status: {status_code} - {status_message}), "
                        f"continuing to poll..."
                    )
                else:
                    raise Exception(
                        f"DataForSEO task failed with status {status_code}: {status_message}"
                    )

            await asyncio.sleep(poll_interval)

        if not data:
            raise Exception("Failed to get results from DataForSEO task")
        if not task_complete:
            raise Exception(
                f"DataForSEO task did not complete within {max_polling_time} seconds"
            )

        # Look for ai_overview item type
        tasks = data.get("tasks", [])
        if not tasks:
            return LLMResponse(
                text=None, tokens_input=0, tokens_output=0,
                model="dataforseo_ai_overview", provider="ai_overview",
                cost_usd=calculate_cost("dataforseo", 0, 0),
            )

        result = tasks[0].get("result", [])
        if not result or not result[0]:
            return LLMResponse(
                text=None, tokens_input=0, tokens_output=0,
                model="dataforseo_ai_overview", provider="ai_overview",
                cost_usd=calculate_cost("dataforseo", 0, 0),
            )

        ai_overview_found = False
        markdown_text = ""
        for item in result[0].get("items") or []:
            if not item:
                continue
            if item.get("type") == "ai_overview":
                ai_overview_found = True
                _filter_ai_overview_urls(item)
                markdown_text = item.get("markdown", "")
                break

        cost = calculate_cost("dataforseo", 0, 0)

        if not ai_overview_found:
            logger.info("[AI Overview] No ai_overview item type found in response")
            return LLMResponse(
                text=None, tokens_input=0, tokens_output=0,
                model="dataforseo_ai_overview", provider="ai_overview",
                cost_usd=cost,
            )

        if not markdown_text:
            logger.info("[AI Overview] ai_overview item found but markdown is empty")
            return LLMResponse(
                text=None, tokens_input=0, tokens_output=0,
                model="dataforseo_ai_overview", provider="ai_overview",
                cost_usd=cost,
            )

        return LLMResponse(
            text=markdown_text,
            tokens_input=0,
            tokens_output=0,
            model="dataforseo_ai_overview",
            provider="ai_overview",
            cost_usd=cost,
        )

    @staticmethod
    def get_gemini_model() -> str:
        """Get Gemini model from environment."""
        return os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    @staticmethod
    def get_perplexity_model() -> str:
        """Get Perplexity model from environment."""
        return os.getenv("PERPLEXITY_MODEL", "sonar-reasoning")


def _extract_llm_scraper_markdown(data: dict, item_type: str) -> str:
    """Extract markdown from a DataForSEO LLM Scraper response (ChatGPT/Gemini).

    Both ChatGPT and Gemini scraper APIs share the same response structure:
    tasks[0].result[0].markdown (top-level) or tasks[0].result[0].items[].markdown
    """
    tasks = data.get("tasks", [])
    if not tasks:
        return ""

    task = tasks[0]
    result = task.get("result", [])
    if not result or not result[0]:
        return ""

    markdown_text = result[0].get("markdown", "")
    if markdown_text:
        return markdown_text

    items = result[0].get("items") or []
    for item in items:
        if not item:
            continue
        if item.get("type") == item_type:
            markdown_text = item.get("markdown", "")
            if markdown_text:
                return markdown_text

    return ""


def _extract_perplexity_response(data: dict) -> str:
    """Extract text + inline citation annotations from a DataForSEO Perplexity LLM Responses result.

    Response structure: tasks[0].result[0].items[0].sections[0].text / .annotations[]
    """
    tasks = data.get("tasks", [])
    if not tasks:
        return ""

    task = tasks[0]
    result = task.get("result", [])
    if not result or not result[0]:
        return ""

    items = result[0].get("items") or []
    if not items:
        return ""

    text_parts = []
    all_annotations = []

    for item in items:
        if not item or item.get("type") != "message":
            continue
        for section in item.get("sections") or []:
            text = section.get("text", "")
            if text:
                text_parts.append(text)
            annotations = section.get("annotations") or []
            all_annotations.extend(annotations)

    content = "\n\n".join(text_parts)

    if all_annotations:
        content = _embed_dataforseo_perplexity_citations(content, all_annotations)

    return content


def _extract_ai_overview_markdown(data: dict) -> str:
    """Extract markdown from a DataForSEO SERP response containing an ai_overview item."""
    tasks = data.get("tasks", [])
    if not tasks:
        return ""

    task = tasks[0]
    result = task.get("result", [])
    if not result or not result[0]:
        return ""

    items = result[0].get("items") or []
    for item in items:
        if not item:
            continue
        if item.get("type") == "ai_overview":
            _filter_ai_overview_urls(item)
            return item.get("markdown", "")

    return ""


def _filter_ai_overview_urls(item: dict):
    """Filter unwanted URLs from an ai_overview item's references (in-place)."""
    references = item.get("references") or []
    if references:
        item["references"] = [
            ref for ref in references
            if ref and not should_filter_url(ref.get("url", ""))
        ]

    for nested_item in item.get("items") or []:
        if not nested_item or "references" not in nested_item:
            continue
        nested_refs = nested_item.get("references") or []
        if nested_refs:
            nested_item["references"] = [
                ref for ref in nested_refs
                if ref and not should_filter_url(ref.get("url", ""))
            ]
