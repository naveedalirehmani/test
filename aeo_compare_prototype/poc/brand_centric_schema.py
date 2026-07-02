"""Proposed BRAND-CENTRIC parsing schema for the AEO redesign POC.

This is the experimental "new design" we want to validate against the current
4-list schema (`models.llm_model.AEOResponseAnalysisSchema`). It is NOT wired
into any production flow — it is only used by the POC script in this folder.

Design (as agreed):
- One `brands[]` list. Each brand carries EVERYTHING about that brand in one
  place: identity, whether it's the target, its citations, and its sentiment.
  No more reconciling the same brand across `target_brand_mentions`,
  `other_brands_mentioned`, and `brand_sentiments` by name.
- `is_target` is only a HINT from the LLM. The POC still determines target
  mention counts/positions deterministically from the raw text, so the
  comparison isolates the *structure*, not the math.
- `key_topics` stays its own list and keeps the brand<->topic edge on the
  TOPIC side only (`topic.brands[]`). We do NOT also put `topics[]` on each
  brand, because the topic phrase is the unstable identity (free-form text)
  and duplicating it would re-introduce the exact join problem we're killing.
- `citation_text` is dropped (redundant with `citation_urls`).
"""

from pydantic import BaseModel, Field, field_validator


class CitationUrlSchema(BaseModel):
    """A single citation URL with its source-type classification."""

    url: str = Field(..., description="The citation URL")
    source_type: str = Field(
        ...,
        description=(
            "Source type: 'owned_media' (brand's own domain), "
            "'earned_media' (third-party site), or 'competitor' "
            "(competitor's own domain)"
        ),
    )


class SentimentDescriptorSchema(BaseModel):
    """A descriptive word/phrase about a brand, with polarity."""

    phrase: str = Field(..., description="Descriptive word or short phrase from the response")
    polarity: str = Field(..., description="Polarity: 'positive', 'neutral', or 'negative'")


class BrandSchema(BaseModel):
    """Everything about ONE brand, grouped together in a single object."""

    brand_name: str = Field(..., description="Name of the brand or website mentioned")
    is_target: bool = Field(
        ...,
        description="True if this is one of the target brands being tracked, False if a competitor/other brand",
    )
    citation_urls: list[CitationUrlSchema] = Field(
        default_factory=list,
        description="All citation URL objects for this brand. Empty list if not cited.",
    )
    sentiment_score: int | None = Field(
        default=None,
        description="Sentiment score 0-100 (81-100 very positive ... 0-20 very negative). Null if no sentiment.",
    )
    sentiment_rating: str | None = Field(
        default=None,
        description="'very positive' | 'positive' | 'neutral' | 'negative' | 'very negative'. Null if no sentiment.",
    )
    sentiment_descriptors: list[SentimentDescriptorSchema] = Field(
        default_factory=list,
        description="Descriptive words/phrases used about this brand, each with polarity. Empty if none.",
    )

    @field_validator("sentiment_descriptors", mode="before")
    @classmethod
    def normalize_descriptors(cls, v: object) -> list[dict]:
        """Accept list of strings or {phrase, polarity} dicts."""
        if not v:
            return []
        result: list[dict] = []
        for item in v:
            if isinstance(item, str):
                result.append({"phrase": item, "polarity": "neutral"})
            elif isinstance(item, dict):
                phrase = item.get("phrase") or item.get("word") or item.get("value") or ""
                result.append({"phrase": str(phrase), "polarity": item.get("polarity", "neutral")})
            elif hasattr(item, "model_dump"):
                result.append(item.model_dump())
            else:
                result.append({"phrase": str(item), "polarity": "neutral"})
        return result

    @field_validator("citation_urls", mode="before")
    @classmethod
    def normalize_citation_urls(cls, v: object) -> list[dict]:
        """Accept list of strings or {url, source_type} dicts."""
        if not v:
            return []
        result: list[dict] = []
        for item in v:
            if isinstance(item, str):
                result.append({"url": item, "source_type": "earned_media"})
            elif isinstance(item, dict):
                result.append(
                    {
                        "url": str(item.get("url", "")),
                        "source_type": item.get("source_type", "earned_media"),
                    }
                )
            elif hasattr(item, "model_dump"):
                result.append(item.model_dump())
            else:
                result.append({"url": str(item), "source_type": "earned_media"})
        return result


class KeyTopicSchema(BaseModel):
    """A key topic. The brand<->topic edge lives HERE (topic side) only."""

    topic: str = Field(
        ...,
        description="Descriptive topic label (3-8 words) using natural industry terminology from the response",
    )
    brands: list[str] = Field(
        default_factory=list,
        description="Brand names explicitly linked to this topic. Empty list if discussed generally.",
    )


class AEOBrandCentricSchema(BaseModel):
    """Brand-centric structured analysis of an LLM response (proposed design)."""

    response_type: str = Field(
        ...,
        description="Type of response: 'list', 'narrative', 'comparison', 'none' (no brands mentioned)",
    )
    brands: list[BrandSchema] = Field(
        default_factory=list,
        description="One entry per brand mentioned, each carrying its citations + sentiment together",
    )
    key_topics: list[KeyTopicSchema] = Field(
        default_factory=list,
        description="Key topics/criteria discussed, each with the brands explicitly linked to it",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "response_type": "list",
                "brands": [
                    {
                        "brand_name": "Notion",
                        "is_target": True,
                        "citation_urls": [
                            {"url": "https://notion.so/startups", "source_type": "owned_media"}
                        ],
                        "sentiment_score": 85,
                        "sentiment_rating": "very positive",
                        "sentiment_descriptors": [
                            {"phrase": "flexible", "polarity": "positive"},
                            {"phrase": "affordable", "polarity": "positive"},
                        ],
                    },
                    {
                        "brand_name": "Asana",
                        "is_target": False,
                        "citation_urls": [
                            {"url": "https://asana.com/use-cases", "source_type": "competitor"}
                        ],
                        "sentiment_score": 65,
                        "sentiment_rating": "positive",
                        "sentiment_descriptors": [
                            {"phrase": "intuitive", "polarity": "positive"},
                            {"phrase": "expensive at scale", "polarity": "negative"},
                        ],
                    },
                ],
                "key_topics": [
                    {"topic": "all-in-one workspace flexibility", "brands": ["Notion"]},
                    {"topic": "task management and timelines", "brands": ["Asana"]},
                ],
            }
        }
