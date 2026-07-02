"""FastAPI app for the AEO structure-comparison prototype.

A standalone tool: you provide a business context + up to N prompts, it fetches
each answer-engine response ONCE, parses it with both the current 4-list design
and the proposed brand-centric design, stores both, and serves a side-by-side UI.

Run (self-contained):

    cd backend/aeo_compare_prototype
    python3.11 -m venv venv && venv/bin/pip install -r requirements.txt
    venv/bin/python -m uvicorn app:app --reload --port 8200

Then open http://localhost:8200
"""

import asyncio
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import analysis
import store

_HERE = os.path.dirname(os.path.abspath(__file__))
_STATIC = os.path.join(_HERE, "static")

app = FastAPI(title="AEO Structure Comparison Prototype", version="0.1.0")


class BusinessIn(BaseModel):
    business_id: str | None = None
    business_name: str = ""
    website_url: str = ""
    brand_names: list[str] = Field(default_factory=list)
    industry: list[str] = Field(default_factory=list)
    products_services: list[str] = Field(default_factory=list)
    business_overview: str | None = None
    unique_selling_proposition: str | None = None


class AnalyzeIn(BaseModel):
    business: BusinessIn
    prompts: list[str]
    providers: list[str] = Field(default_factory=lambda: [analysis.DEFAULT_PROVIDER])


@app.get("/api/providers")
async def get_providers() -> dict:
    return {
        "providers": analysis.available_providers(),
        "default": analysis.DEFAULT_PROVIDER,
        "default_business_id": analysis.DEFAULT_BUSINESS_ID,
    }


@app.get("/api/business/{business_id}")
async def get_business(business_id: str) -> dict:
    prefill = await analysis.fetch_business_prefill(business_id)
    if not prefill:
        raise HTTPException(status_code=404, detail=f"Business {business_id} not found")
    return prefill


@app.post("/api/analyze")
async def analyze(body: AnalyzeIn) -> dict:
    prompts = [p.strip() for p in body.prompts if p and p.strip()]
    if not prompts:
        raise HTTPException(status_code=400, detail="Provide at least one prompt")
    providers = body.providers or [analysis.DEFAULT_PROVIDER]

    business_profile, target_brand_names = await analysis.resolve_business(
        body.business.model_dump()
    )

    analysis.logger.info(
        f"START analyze: {len(prompts)} prompt(s) x {len(providers)} provider(s) "
        f"= {len(prompts) * len(providers)} fetches + {2 * len(prompts) * len(providers)} parses | "
        f"brands={target_brand_names}"
    )

    # One task per (prompt, provider); each fetches its raw response once.
    async def run_prompt(prompt_text: str) -> dict:
        analysis.logger.info(f"prompt: '{prompt_text[:60]}'")
        provider_results = await asyncio.gather(
            *[
                analysis.analyze_one(
                    prompt_text, provider, business_profile, target_brand_names
                )
                for provider in providers
            ]
        )
        return {"prompt_text": prompt_text, "providers": list(provider_results)}

    prompt_blocks = await asyncio.gather(*[run_prompt(p) for p in prompts])
    analysis.logger.info("all prompts analyzed; saving session...")

    session = {
        "business_name": business_profile.get("business_name"),
        "business": business_profile,
        "target_brand_names": target_brand_names,
        "providers": providers,
        "prompts": list(prompt_blocks),
    }
    saved = await store.create_session(session)
    analysis.logger.info(f"DONE: saved session {saved.get('id')}")
    return saved


@app.post("/api/sessions/{session_id}/reparse")
async def reparse(session_id: str) -> dict:
    """Re-run BOTH parses using the stored raw responses (no new fetches).

    Useful for iterating on the brand-centric schema/prompt without spending on
    DataForSEO again. Saves the result as a NEW session linked via reparse_of.
    """
    src = await store.get_session(session_id)
    if not src:
        raise HTTPException(status_code=404, detail="Session not found")

    business_profile = src.get("business", {})
    target_brand_names = src.get("target_brand_names", [])

    async def run_prompt(block: dict) -> dict:
        async def redo(pr: dict) -> dict:
            raw = pr.get("raw_response")
            if not raw:
                return pr  # nothing to reparse
            return await analysis.analyze_one(
                block["prompt_text"],
                pr["provider"],
                business_profile,
                target_brand_names,
                raw_response=raw,
            )

        provider_results = await asyncio.gather(*[redo(pr) for pr in block.get("providers", [])])
        return {"prompt_text": block["prompt_text"], "providers": list(provider_results)}

    prompt_blocks = await asyncio.gather(*[run_prompt(b) for b in src.get("prompts", [])])

    session = {
        "business_name": src.get("business_name"),
        "business": business_profile,
        "target_brand_names": target_brand_names,
        "providers": src.get("providers", []),
        "prompts": list(prompt_blocks),
        "reparse_of": session_id,
    }
    return await store.create_session(session)


@app.get("/api/sessions")
async def sessions() -> dict:
    return {"sessions": await store.list_sessions()}


@app.get("/api/sessions/{session_id}")
async def session_detail(session_id: str) -> dict:
    doc = await store.get_session(session_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")
    return doc


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(os.path.join(_STATIC, "index.html"))


app.mount("/static", StaticFiles(directory=_STATIC), name="static")
