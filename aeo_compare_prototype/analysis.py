"""Analysis orchestration for the structure-comparison prototype.

This app is fully self-contained: the analysis modules it needs (DataForSEO
fetch, instructor parsing, the current metrics calculator) and the brand-centric
modules under ``poc/`` are vendored into this package. This file is the thin
orchestration that runs BOTH designs over the SAME raw response.

Key guarantee: the answer-engine response is fetched ONCE per (prompt, provider)
and fed to both parsers, so the only thing that differs between the two results
is the instructor call (schema + prompt) and everything downstream of it.
"""

import asyncio
import logging
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# Ensure the app's own directory is importable regardless of the current working
# directory, so the vendored packages (config/services/repos/poc/...) resolve.
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from dotenv import load_dotenv

# Load this app's own .env (harmless no-op if absent, e.g. when env vars are
# injected directly via `docker run --env-file`).
load_dotenv(os.path.join(_HERE, ".env"))

import services.metrics_calculator as mc  # noqa: E402
from config.llm_config import LLMConfig  # noqa: E402
from config.provider_configs import get_provider_configs  # noqa: E402
from repos import business_repo  # noqa: E402
from services.instructor_service import InstructorService  # noqa: E402
from services.llm_service import LLMService  # noqa: E402

from poc.brand_centric_analytics import (  # noqa: E402
    build_brand_centric_analytics,
    old_sentiment_join_report,
)
from poc.brand_centric_prompt import build_brand_centric_parsing_prompt  # noqa: E402
from poc.brand_centric_schema import AEOBrandCentricSchema  # noqa: E402

# Dedicated logger with its own stdout handler so progress always shows in the
# terminal regardless of uvicorn's logging config.
logger = logging.getLogger("aeo_compare")
if not logger.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("%(asctime)s [aeo_compare] %(message)s", "%H:%M:%S"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)
    logger.propagate = False

DEFAULT_PROVIDER = "chatgpt"

# Pre-seeded business profile to load into the UI on startup.
# NOTE: the Reddit profile (696e3ecf1c866792c3a14b56) lives in the REMOTE DB,
# not the local one this .env points to. Default to a business that actually
# exists locally (Facebook, which also has tracked prompts). Override via the
# DEFAULT_BUSINESS_ID env var, or just paste any id in the UI field.
DEFAULT_BUSINESS_ID = os.getenv("DEFAULT_BUSINESS_ID", "692120f6726e168041cad5b0")


def available_providers() -> list[str]:
    return list(get_provider_configs().keys())


async def fetch_business_prefill(business_id: str) -> dict | None:
    """Fetch a business profile from the local DB and return UI prefill fields."""
    doc = await business_repo.get_business_by_id(business_id)
    if not doc:
        return None
    return {
        "business_id": str(doc.get("_id")),
        "business_name": doc.get("business_name", ""),
        "website_url": doc.get("website_url", ""),
        "brand_names": doc.get("brand_names") or [],
        "industry": doc.get("industry") or [],
        "products_services": doc.get("products_services") or [],
        "business_overview": doc.get("business_overview") or "",
    }


async def resolve_business(payload: dict) -> tuple[dict, list[str]]:
    """Resolve the business profile + target brand names for parsing context.

    If ``business_id`` is provided and found in the local DB, that profile is
    used (so brand data matches production). Otherwise the manually entered
    fields are used.

    Returns:
        (business_profile_dict, target_brand_names)
    """
    business_id = (payload.get("business_id") or "").strip()
    if business_id:
        doc = await business_repo.get_business_by_id(business_id)
        if doc:
            profile = dict(doc)
            names: list[str] = []
            if profile.get("business_name"):
                names.append(profile["business_name"])
            for bn in profile.get("brand_names") or []:
                if bn and bn not in names:
                    names.append(bn)
            return profile, (names or ["Your Brand"])

    # Manual fields
    profile = {
        "business_name": payload.get("business_name") or "Unknown Business",
        "website_url": payload.get("website_url") or "",
        "industry": payload.get("industry") or [],
        "products_services": payload.get("products_services") or [],
        "business_overview": payload.get("business_overview") or None,
        "unique_selling_proposition": payload.get("unique_selling_proposition") or None,
        "brand_names": payload.get("brand_names") or [],
    }
    names = [profile["business_name"]] if profile["business_name"] else []
    for bn in profile["brand_names"]:
        if bn and bn not in names:
            names.append(bn)
    return profile, (names or ["Your Brand"])


async def _parse_brand_centric(
    provider: str,
    raw_response: str,
    target_brand_names: list[str],
    business_profile: dict,
) -> AEOBrandCentricSchema:
    """Parse a raw response with the PROPOSED brand-centric schema."""
    client = LLMConfig.get_openai_client()
    if not client:
        raise RuntimeError("OpenAI client not initialized (set OPENAI_API_KEY)")

    prompt = build_brand_centric_parsing_prompt(
        provider, raw_response, target_brand_names, business_profile
    )
    return await asyncio.to_thread(
        client.chat.completions.create,
        model="gpt-5-mini",
        response_model=AEOBrandCentricSchema,
        messages=[
            {
                "role": "system",
                "content": "You are an expert at analyzing text and extracting structured information about brand mentions, citations, and positioning.",
            },
            {"role": "user", "content": prompt},
        ],
    )


async def analyze_one(
    prompt_text: str,
    provider: str,
    business_profile: dict,
    target_brand_names: list[str],
    raw_response: str | None = None,
) -> dict:
    """Run BOTH designs over one (prompt, provider).

    Fetches the raw response once (unless ``raw_response`` is supplied for a
    re-parse), then parses it with the current 4-list schema and the proposed
    brand-centric schema, computing the comparable metrics for each.
    """
    provider_configs = get_provider_configs()
    cfg = provider_configs.get(provider)
    if not cfg:
        return {"provider": provider, "error": f"Unknown provider '{provider}'"}

    snippet = prompt_text[:50].replace("\n", " ")

    try:
        if raw_response is None:
            logger.info(f"[{provider}] fetching response for '{snippet}'...")
            llm_response = await LLMService.get_llm_response(
                prompt_text, provider, cfg["model"]
            )
            raw_response = llm_response.text
            logger.info(f"[{provider}] fetched {len(raw_response or '')} chars")
        else:
            logger.info(f"[{provider}] reusing stored response ({len(raw_response)} chars)")
    except Exception as e:
        logger.warning(f"[{provider}] fetch FAILED: {e}")
        return {"provider": provider, "error": f"Fetch failed: {e}"}

    if not raw_response:
        logger.warning(f"[{provider}] empty response")
        return {"provider": provider, "error": "Empty response from provider"}

    result: dict = {"provider": provider, "raw_response": raw_response}

    # CURRENT design
    try:
        logger.info(f"[{provider}] instructor parse #1 (current 4-list)...")
        old_parsed = await InstructorService.parse_provider_response(
            provider, raw_response, target_brand_names, business_profile
        )
        metrics = mc.calculate_metrics(old_parsed, target_brand_names, raw_response)
        result["current_design"] = {
            "parsed": old_parsed.model_dump(),
            "metrics": metrics,
            "sentiment_join_report": old_sentiment_join_report(old_parsed),
        }
        logger.info(
            f"[{provider}] current done: target={metrics['target_brand_mentioned']} "
            f"mentions={metrics['target_brand_mention_count']} SOV={metrics['share_of_voice']}%"
        )
    except Exception as e:
        logger.warning(f"[{provider}] current parse FAILED: {e}")
        result["current_design"] = {"error": f"Parse failed: {e}"}

    # PROPOSED design
    try:
        logger.info(f"[{provider}] instructor parse #2 (brand-centric)...")
        new_parsed = await _parse_brand_centric(
            provider, raw_response, target_brand_names, business_profile
        )
        analytics = build_brand_centric_analytics(
            new_parsed, target_brand_names, raw_response
        )
        result["proposed_design"] = {
            "parsed": new_parsed.model_dump(),
            "analytics": analytics,
        }
        logger.info(
            f"[{provider}] proposed done: brands={analytics['brand_count']} "
            f"SOV={analytics['share_of_voice']}%"
        )
    except Exception as e:
        logger.warning(f"[{provider}] proposed parse FAILED: {e}")
        result["proposed_design"] = {"error": f"Parse failed: {e}"}

    return result
