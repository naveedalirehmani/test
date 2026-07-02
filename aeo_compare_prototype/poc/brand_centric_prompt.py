"""Brand-centric parsing prompt for the AEO redesign POC.

This intentionally reuses the SAME instructions as the production prompt
(`prompts.aeo_prompts.build_provider_parsing_prompt`) for:
  - competitor identification (the industry-relevance decision framework)
  - citation source-type classification
  - sentiment scoring + descriptors
  - key-topic extraction

The ONLY thing that changes is the OUTPUT STRUCTURE: instead of asking the
model to scatter a brand across `target_brand_mentions`, `other_brands_mentioned`
and `brand_sentiments`, we ask it to emit ONE object per brand carrying
everything about that brand. Key topics keep their own list with the edge on
the topic side.
"""


def build_brand_centric_parsing_prompt(
    provider: str,
    response: str,
    target_brand_names: list[str],
    business_profile: dict,
) -> str:
    """Build the brand-centric parsing prompt (same rules, grouped output)."""
    brand_names_str = ", ".join(target_brand_names)
    provider_upper = provider.upper()

    brand_name = business_profile.get("business_name", "Unknown Business")
    industry = ", ".join(business_profile.get("industry", [])) or "General"
    products_services = (
        ", ".join(business_profile.get("products_services", []))
        or "Various products and services"
    )
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

YOUR OUTPUT STRUCTURE (IMPORTANT):
Return ONE list called `brands`. Each entry is a SINGLE brand and must contain
EVERYTHING about that brand together: its name, whether it is a target brand,
its citation URLs (with source types), and its sentiment (score, rating,
descriptors). Handle one brand completely before moving to the next. Do NOT
split a brand's information across multiple lists, and do NOT repeat a brand.
Separately, return a `key_topics` list (topics can span multiple brands).

Instructions:

1. **Identify Every Brand (target + competitors)**:
   - Include any of the target brands ({brand_names_str}) that are mentioned, and
     set `is_target` = true for them.
   - For all OTHER brands, apply this decision framework and set `is_target` = false:
     For each brand mentioned, ask:
     a) Does this brand operate in "{industry}"?
     b) Does this brand offer solutions for: {products_services}?
     c) Would a customer researching this industry compare these brands as alternatives?

     If YES to these questions → Include the brand.

     If UNCERTAIN, check the relationship:
     - Does {brand_name} USE this brand as a tool/platform?
     - Does {brand_name} SELL this brand's products?
     - Does {brand_name} integrate WITH or run ON this brand?
     - Does {brand_name} sell THROUGH this brand?

     If YES to any relationship question → Exclude the brand.

   Key principle: Extract brands that compete for the same customer decision, not
   brands that are part of the ecosystem or value chain.

2. **Citation URLs (with Source Type Classification)** — per brand, in `citation_urls`:
   For each brand, extract ALL URLs that cite or reference the brand. For each URL,
   classify its `source_type`:

   **Source Types:**
   - `owned_media` — URL belongs to the brand's own website/domain or a subdomain of it
   - `earned_media` — URL is from a third-party site that is NOT a direct competitor
     (news articles, review sites, comparison sites, directories, Wikipedia, Forbes, etc.)
   - `competitor` — URL belongs to a direct competitor's own website/domain

   **CRITICAL — Owned Media Rule:**
   The target brand's website is: {website_url}
   Only classify a URL as `owned_media` if its domain exactly matches the target
   brand's website domain or is a subdomain of it (e.g., blog.example.com when the
   website is example.com). If a URL's domain does NOT match, classify it as
   `earned_media` or `competitor` instead. When in doubt, default to `earned_media`.

   Each entry in `citation_urls` is an object: {{"url": "<the URL>", "source_type": "<owned_media|earned_media|competitor>"}}
   If a brand is not cited, `citation_urls` is an empty list [].

3. **Sentiment** — per brand, set `sentiment_score`, `sentiment_rating`, `sentiment_descriptors`:

   A. **Sentiment Score & Rating** (one per brand):
   Score how the brand is portrayed (0–100) and assign the corresponding rating:
   - 81–100 → `very positive`: Strongly endorsed, highlighted as a top choice
   - 61–80  → `positive`: Mentioned favorably, positive attributes noted
   - 41–60  → `neutral`: Factual description, no strong opinion either way
   - 21–40  → `negative`: Mentioned with reservations, drawbacks noted
   - 0–20   → `very negative`: Explicitly discouraged, strong negative language

   B. **Sentiment Descriptors** (variable length per brand):
   Extract descriptive words and short phrases actually used about this brand.
   - Include adjectives/characterizations (e.g., "reliable", "enterprise-grade", "lacking in features")
   - Include both positive AND negative descriptors with polarity: `positive` | `neutral` | `negative`
   - Only extract language actually present or clearly implied — do NOT invent descriptors
   - Only include descriptors that directly describe THIS brand/product/service
   - If no descriptive language, return an empty array []
   - Deduplicate: include each descriptor only once per brand

   **Calibration:**
   ✓ "reliable", "enterprise-grade", "budget-friendly", "limited integrations"
   ✗ "good" ← too vague; use the actual words from the response
   ✗ "the best CRM software for enterprises" ← too long; extract the descriptive parts only

4. **Extract Key Topics** — in `key_topics` (separate from brands):
   Extract every distinct topic, criterion, or evaluation factor discussed.

   For each topic:
   A. **Topic Label**: A descriptive phrase (3–8 words) using natural industry terminology
   B. **Brands Associated**: List of brand names explicitly linked to this topic. Only
      include brands directly connected — if discussed generally, return an empty array [].
      Use the SAME brand name strings you used in the `brands` list above.

   **Output format:** {{"topic": "24/7 technical support availability", "brands": ["KONE", "TK Elevator"]}}

   **Calibration:**
   ✓ "Microsoft 365 email integration", "24/7 technical support", "per-user monthly pricing"
   ✗ "integration" ← too vague
   ✗ "This platform offers comprehensive integration capabilities" ← too long

5. **response_type**: one of 'list', 'narrative', 'comparison', or 'none' (no brands mentioned).

---

{provider_upper} RESPONSE:
{response}

---

Extract the information in the brand-centric structured format described above."""
