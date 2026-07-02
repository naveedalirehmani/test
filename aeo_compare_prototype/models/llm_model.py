"""LLM models - Pydantic models for LLM response parsing.

MIRRORS zicy-tools AEOResponseAnalysisSchema to ensure consistency
between initial analysis and re-analysis.

Includes simplified sentiment analysis with score, rating, and descriptors
per brand (target and competitors).
"""

from pydantic import BaseModel, Field, field_validator


class CitationUrlSchema(BaseModel):
    """Schema for a single citation URL with source type classification."""

    url: str = Field(..., description="The citation URL")
    source_type: str = Field(
        ...,
        description="Source type: 'owned_media' (brand's own domain), 'earned_media' (third-party site), or 'competitor' (competitor's own domain)",
    )


class SentimentDescriptorSchema(BaseModel):
    """Schema for a sentiment descriptor — a word or short phrase describing a brand."""

    phrase: str = Field(..., description="Descriptive word or short phrase from the response")
    polarity: str = Field(
        ...,
        description="Polarity: 'positive', 'neutral', or 'negative'",
    )


class BrandSentimentSchema(BaseModel):
    """Schema for sentiment per brand — single score + rating + descriptors."""

    brand_name: str = Field(..., description="Name of the brand")
    sentiment_score: int = Field(
        ...,
        description="Sentiment score 0-100. 81-100=very positive, 61-80=positive, 41-60=neutral, 21-40=negative, 0-20=very negative",
    )
    sentiment_rating: str = Field(
        ...,
        description="Qualitative rating corresponding to the score: 'very positive', 'positive', 'neutral', 'negative', 'very negative'",
    )
    sentiment_descriptors: list[SentimentDescriptorSchema] = Field(
        default_factory=list,
        description="Descriptive words and short phrases used about this brand, each with polarity. Empty list if no descriptive language.",
    )

    @field_validator("sentiment_descriptors", mode="before")
    @classmethod
    def normalize_descriptors(cls, v: object) -> list[dict]:
        """Accept list of strings or list of {phrase, polarity} dicts."""
        if not v:
            return []
        result: list[dict] = []
        for item in v:
            if isinstance(item, str):
                result.append({"phrase": item, "polarity": "neutral"})
            elif isinstance(item, dict):
                phrase = item.get("phrase") or item.get("word") or item.get("value") or ""
                polarity = item.get("polarity", "neutral")
                result.append({"phrase": str(phrase), "polarity": polarity})
            elif hasattr(item, "model_dump"):
                result.append(item.model_dump())
            else:
                result.append({"phrase": str(item), "polarity": "neutral"})
        return result


class KeyTopicSchema(BaseModel):
    """Schema for a key topic extracted from the response."""

    topic: str = Field(
        ...,
        description="Descriptive topic label (3-8 words) using natural industry terminology from the response",
    )
    brands: list[str] = Field(
        default_factory=list,
        description="Brand names explicitly linked to this topic in the response. Empty list if discussed generally.",
    )


class BrandMentionSchema(BaseModel):
    """Schema for a single brand mention in LLM response.

    The LLM only identifies brands and their citations.
    Counts and positions are calculated manually from raw response.
    """

    brand_name: str = Field(
        ...,
        description="Name of the brand or website mentioned",
    )
    citation_urls: list[CitationUrlSchema] = Field(
        default_factory=list,
        description="List of citation URL objects for this brand, each with url and source_type (owned_media, earned_media, or competitor). Empty list if not cited.",
    )
    citation_text: str | None = Field(
        default=None,
        description="The primary citation text or source reference if cited",
    )

    @field_validator("citation_urls", mode="before")
    @classmethod
    def normalize_citation_urls(cls, v: object) -> list[dict]:
        """Accept list of strings or list of {url, source_type} dicts for backward compatibility."""
        if not v:
            return []
        result: list[dict] = []
        for item in v:
            if isinstance(item, str):
                # Backward compatibility: plain string URLs default to earned_media
                result.append({"url": item, "source_type": "earned_media"})
            elif isinstance(item, dict):
                url = item.get("url", "")
                source_type = item.get("source_type", "earned_media")
                result.append({"url": str(url), "source_type": source_type})
            elif hasattr(item, "model_dump"):
                result.append(item.model_dump())
            else:
                result.append({"url": str(item), "source_type": "earned_media"})
        return result


class AEOResponseAnalysisSchema(BaseModel):
    """Structured analysis of an LLM response for AEO tracking.

    SIMPLIFIED: LLM only identifies brands, citations, sentiment, and response type.
    All metrics are calculated manually from raw response for accuracy.
    """

    brand_sentiments: list[BrandSentimentSchema] = Field(
        default_factory=list,
        description="Sentiment per brand: score (0-100), rating, and descriptors with polarity",
    )
    response_type: str = Field(
        ...,
        description="Type of response: 'list', 'narrative', 'comparison', 'none' (no brands mentioned)",
    )
    target_brand_mentions: list[BrandMentionSchema] = Field(
        default_factory=list,
        description="All mentions of the target brand with their citations (if any)",
    )
    other_brands_mentioned: list[BrandMentionSchema] = Field(
        default_factory=list,
        description="All other brands/websites/companies mentioned with their citations",
    )
    key_topics: list[KeyTopicSchema] = Field(
        default_factory=list,
        description="Key topics, criteria, and evaluation factors discussed in the response, each with associated brand names",
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "brand_sentiments": [
                    {
                        "brand_name": "KONE",
                        "sentiment_score": 82,
                        "sentiment_rating": "very positive",
                        "sentiment_descriptors": [
                            {"phrase": "high safety standards", "polarity": "positive"},
                            {"phrase": "major global manufacturer", "polarity": "positive"},
                            {"phrase": "expensive", "polarity": "negative"},
                        ],
                    }
                ],
                "response_type": "list",
                "target_brand_mentions": [
                    {
                        "brand_name": "KONE",
                        "citation_urls": [
                            {"url": "https://kone.com/elevators", "source_type": "owned_media"},
                            {"url": "https://voiceofasean.com/kone-article", "source_type": "earned_media"},
                        ],
                        "citation_text": "https://kone.com/elevators",
                    }
                ],
                "other_brands_mentioned": [
                    {
                        "brand_name": "TK Elevator",
                        "citation_urls": [
                            {"url": "https://tkelevator.com/about", "source_type": "competitor"},
                        ],
                        "citation_text": "https://tkelevator.com/about",
                    }
                ],
                "key_topics": [
                    {"topic": "after-sales maintenance support", "brands": ["TK Elevator", "GGEAR Elevator"]},
                    {"topic": "international safety certifications", "brands": ["KONE"]},
                    {"topic": "cost-effective local service", "brands": ["Diamond Elevator"]},
                ],
            }
        }
