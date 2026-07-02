"""Prompt templates for AEO analysis service.

MIRRORS zicy-tools prompt templates to ensure consistency.
Any changes to prompt logic should be synchronized between both codebases.

Uses per-provider parsing with multi-dimensional sentiment analysis.
"""


def build_provider_parsing_prompt(
    provider: str,
    response: str,
    target_brand_names: list[str],
    business_profile: dict,
) -> str:
    """
    Build parsing prompt for a single provider's response analysis with business context.

    The LLM only needs to identify:
    1. Sentiment toward target brand
    2. Response type (list, narrative, comparison, none)
    3. Target brand mentions with citations
    4. Other brands mentioned with citations

    All metrics (counts, positions, share of voice) are calculated manually
    from the raw response text for accuracy and consistency.

    Args:
        provider: Provider name (e.g., "chatgpt", "gemini")
        response: The raw response text from the provider
        target_brand_names: List of target brand names
        business_profile: Full business profile dict for context

    Returns:
        str: Formatted prompt for instructor parsing
    """
    brand_names_str = ", ".join(target_brand_names)
    provider_upper = provider.upper()

    # Extract business profile fields with safe fallbacks
    brand_name = business_profile.get("business_name", "Unknown Business")
    industry = ", ".join(business_profile.get("industry", [])) or "General"
    products_services = (
        ", ".join(business_profile.get("products_services", []))
        or "Various products and services"
    )

    # Use business_overview as main goal, fallback to unique_selling_proposition
    main_goal = (
        business_profile.get("business_overview")
        or business_profile.get("unique_selling_proposition")
        or "Providing value to customers"
    )

    website_url = business_profile.get("website_url", "")

    return f"""You are analyzing a response from the {provider_upper} LLM provider.

TARGET BRANDS TO TRACK: {brand_names_str}

BUSINESS CONTEXT:
Brand Name: {brand_name}
Website: {website_url}
Industry: {industry}
Main Products/Services: {products_services}
Main Goal/Problem Solved: {main_goal}

Instructions:

1. **Identify Target Brand Mentions**:
   - Check if any of the target brands ({brand_names_str}) are mentioned
   - For each target brand mention found, extract citation URLs if any

2. **Identify Other Brands (Competitors)**:
   Extract ONLY brands relevant to this industry by applying this decision framework:
   For each brand mentioned, ask:
   a) Does this brand operate in "{industry}"?
   b) Does this brand offer solutions for: {products_services}?
   c) Would a customer researching this industry compare these brands as alternatives?

   If YES to these questions → Include the brand

   If UNCERTAIN, check the relationship:
   - Does {brand_name} USE this brand as a tool/platform?
   - Does {brand_name} SELL this brand's products?
   - Does {brand_name} integrate WITH or run ON this brand?
   - Does {brand_name} sell THROUGH this brand?

   If YES to any relationship question → Exclude the brand

   Key principle: Extract brands that compete for the same customer decision, not brands that are part of the ecosystem or value chain.

3. **Extract Citation URLs (with Source Type Classification)**:
   For each brand, extract ALL URLs that cite or reference the brand. For each URL, classify its `source_type`:

   **Source Types:**
   - `owned_media` — URL belongs to the brand's own website/domain or a subdomain of it
   - `earned_media` — URL is from a third-party site that is NOT a direct competitor (e.g., news articles, review sites, comparison sites, directories, Wikipedia, Forbes, industry publications)
   - `competitor` — URL belongs to a direct competitor's own website/domain

   **CRITICAL — Owned Media Rule:**
   The target brand's website is: {website_url}
   Only classify a URL as `owned_media` if its domain exactly matches the target brand's website domain or is a subdomain of it (e.g., blog.example.com when the website is example.com).
   If a URL's domain does NOT match the brand's website domain, it MUST NOT be classified as `owned_media` — classify it as `earned_media` or `competitor` instead.
   When in doubt, default to `earned_media`.

   **What to extract:**
   - URLs from the brand's own website domain or subdomains (→ owned_media)
   - Direct links to the brand's official pages, products, or services on their own domain (→ owned_media)
   - Third-party sources that mention the brand, e.g., news sites, review/comparison sites, research reports (→ earned_media)
   - URLs like wikipedia.org, forbes.com, techcrunch.com, etc. that talk ABOUT the brand (→ earned_media)
   - Aggregator or directory sites that list multiple brands (→ earned_media)
   - URLs from a direct competitor's own website/domain (→ competitor)

   **Output format per URL:**
   Each entry in citation_urls should be an object: {{"url": "<the URL>", "source_type": "<owned_media|earned_media|competitor>"}}

   If a brand has multiple citation URLs, list all of them with their source_type.
   If a brand is not cited, citation_urls should be an empty list []

4. **Assess Brand Sentiment:**
   For **each target brand and competitor** mentioned in the response, extract:

   A. **Sentiment Score & Rating** (one per brand):
   Score how the brand is portrayed (0–100) and assign the corresponding rating:
   - 81–100 → `very positive`: Strongly endorsed, highlighted as a top choice, clear recommendation
   - 61–80  → `positive`: Mentioned favorably, positive attributes noted, recommended with caveats
   - 41–60  → `neutral`: Mentioned neutrally, factual description, no strong opinion either way
   - 21–40  → `negative`: Mentioned with reservations, drawbacks noted, not preferred
   - 0–20   → `very negative`: Explicitly discouraged, strong negative language, warned against

   B. **Sentiment Descriptors** (variable length per brand):
   Extract descriptive words and short phrases actually used about this brand.
   - Include adjectives, characterizations, and evaluative phrases (e.g., "reliable", "enterprise-grade", "lacking in features")
   - Include both positive AND negative descriptors with polarity: `positive` | `neutral` | `negative`
   - Only extract language actually present or clearly implied in the text — do NOT invent descriptors
   - Only include descriptors that directly describe the brand, product, or service, not unrelated entities
   - If the brand is mentioned with no descriptive language, return an empty array []
   - Deduplicate: include each descriptor only once per brand

   **Calibration:**
   ✓ "reliable", "enterprise-grade", "budget-friendly", "limited integrations" ← specific, extracted from text
   ✗ "good" ← too vague; use the actual words from the response
   ✗ "the best CRM software for enterprises" ← too long; extract the descriptive parts only

   **Output format per brand:**
   {{"brand_name": "KONE", "sentiment_score": 82, "sentiment_rating": "very positive", "sentiment_descriptors": [{{"phrase": "high safety standards", "polarity": "positive"}}, {{"phrase": "expensive", "polarity": "negative"}}]}}

5. **Extract Key Topics:**
   Extract every distinct topic, criterion, or evaluation factor discussed in the response.

   For each topic:
   A. **Topic Label**: A descriptive phrase (3–8 words) using natural industry terminology found in the response
   B. **Brands Associated**: List of brand names explicitly linked to this topic in the response.
      Only include brands directly connected — if discussed generally, return an empty array []

   **Output format:**
   {{"topic": "24/7 technical support availability", "brands": ["KONE", "TK Elevator"]}}

   - Use the same brand name strings as identified in Steps 1 and 2

   **Calibration:**
   ✓ "Microsoft 365 email integration", "24/7 technical support", "per-user monthly pricing"
   ✗ "integration" ← too vague
   ✗ "This platform offers comprehensive integration capabilities" ← too long

---

{provider_upper} RESPONSE:
{response}

---

Extract the information in structured format."""
