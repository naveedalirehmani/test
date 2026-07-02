"""AEO Metrics Calculator - Manual calculation of metrics from raw response.

All metrics are calculated manually from the raw response text for consistency
and accuracy. The LLM only identifies brands and citations.

Metrics calculated:
- Target brand mention count (word boundary string matching with overlap & proximity detection)
- Other brands count (length of array)
- Brand positions (order of first appearance)
- Share of voice (target / total)
- Competitor mentions list
- Citations list

Features:
- Smart word boundary matching for special characters (parentheses, periods, etc.)
- Unicode-aware matching for non-English languages (Chinese, Japanese, Arabic, Cyrillic, etc.)
- Overlap detection to prevent double-counting of brand name variations
- Proximity detection to prevent counting acronyms/abbreviations as separate mentions
  (e.g., "AIMS Data Centre (ACD)" counts as 1 mention, not 2)

This file mirrors the zicy-tools metrics calculator to ensure consistency
between initial analysis and re-analysis.
"""

import re
import unicodedata
from datetime import datetime, timezone


def is_unicode_alnum(char: str) -> bool:
    """
    Check if a character is alphanumeric in any language (Unicode-aware).

    This includes:
    - ASCII letters and numbers (a-z, A-Z, 0-9)
    - Letters from all languages (Chinese, Japanese, Arabic, Cyrillic, etc.)
    - Numbers from all scripts

    Args:
        char: A single character to check

    Returns:
        True if the character is alphanumeric in any language, False otherwise
    """
    if not char:
        return False

    # Get Unicode category - letters (L*) and numbers (N*) are considered alphanumeric
    category = unicodedata.category(char)
    return category.startswith("L") or category.startswith("N")


def is_cjk_char(char: str) -> bool:
    """
    Check if a character is a CJK (Chinese, Japanese, Korean) character.

    CJK languages don't use spaces between words, so they require different
    word boundary handling.

    Args:
        char: A single character to check

    Returns:
        True if the character is a CJK character, False otherwise
    """
    if not char:
        return False

    code_point = ord(char)

    # CJK Unified Ideographs: U+4E00 to U+9FFF (most common Chinese characters)
    # CJK Unified Ideographs Extension A: U+3400 to U+4DBF
    # CJK Unified Ideographs Extension B-F: U+20000 to U+2EBEF
    # Hiragana: U+3040 to U+309F
    # Katakana: U+30A0 to U+30FF
    # Hangul Syllables: U+AC00 to U+D7AF

    return (
        (0x4E00 <= code_point <= 0x9FFF)  # CJK Unified Ideographs
        or (0x3400 <= code_point <= 0x4DBF)  # CJK Extension A
        or (0x3040 <= code_point <= 0x309F)  # Hiragana
        or (0x30A0 <= code_point <= 0x30FF)  # Katakana
        or (0xAC00 <= code_point <= 0xD7AF)  # Hangul
        or (0x20000 <= code_point <= 0x2EBEF)  # CJK Extensions B-F
    )


def contains_cjk(text: str) -> bool:
    """
    Check if a text string contains any CJK (Chinese, Japanese, Korean) characters.

    This is used to determine if CJK-friendly word boundaries should be used.
    Even mixed-language strings like "Apple 公司" should use CJK boundaries
    because they appear in CJK text contexts without clear word boundaries.

    Args:
        text: The text to check

    Returns:
        True if the text contains any CJK characters, False otherwise
    """
    if not text:
        return False

    # Check if any character is CJK
    for char in text:
        if is_cjk_char(char):
            return True

    return False


def count_brand_occurrences(
    raw_response: str, brand_name: str, use_word_boundary: bool = True
) -> int:
    """
    Count occurrences of a brand name in the raw response text.
    Uses case-sensitive matching with smart word boundary handling.

    Args:
        raw_response: The raw LLM response text
        brand_name: The brand name to search for
        use_word_boundary: If True, only match whole words (default: True)

    Returns:
        Number of times the brand name appears in the text
    """
    if not raw_response or not brand_name:
        return 0

    if use_word_boundary:
        pattern = _build_smart_word_boundary_pattern(brand_name)
        matches = re.findall(pattern, raw_response, re.IGNORECASE)
        return len(matches)
    else:
        # Simple substring matching (case-insensitive)
        return raw_response.lower().count(brand_name.lower())


def _build_smart_word_boundary_pattern(brand_name: str) -> str:
    """
    Build a regex pattern with smart word boundary handling.
    Handles special characters correctly and supports Unicode/non-English characters.

    Uses Unicode-aware matching to properly handle brand names in any language:
    - ASCII: "Apple", "Microsoft"
    - Chinese: "品牌名称"
    - Japanese: "ブランド"
    - Arabic: "علامة تجارية"
    - Cyrillic: "бренд"
    - Mixed: "Apple 公司"

    Special handling for CJK (Chinese, Japanese, Korean) languages:
    - CJK languages don't use spaces between words
    - Uses exact string matching without strict word boundaries
    - Still prevents matching within ASCII words (e.g., "Apple" in "PineApple")

    Args:
        brand_name: The brand name to create a pattern for

    Returns:
        Regex pattern string with proper Unicode-aware word boundaries
    """
    # Escape the brand name for regex
    escaped_name = re.escape(brand_name)

    # Special handling for CJK text (Chinese, Japanese, Korean)
    # These languages don't use spaces, so traditional word boundaries don't apply
    # This includes mixed-language brands like "Apple 公司"
    if contains_cjk(brand_name):
        # For CJK or CJK-containing text, we don't enforce strict word boundaries
        # This allows matching "苹果公司" in "苹果公司是一家很好的公司"
        # and "Apple 公司" in "Apple 公司是一家很好的公司"
        # even though there's no space after the brand name
        # We only prevent matching within ASCII words
        left_boundary = r"(?<![a-zA-Z0-9])"
        right_boundary = r"(?![a-zA-Z0-9])"
        return left_boundary + escaped_name + right_boundary

    # For non-CJK text (ASCII, Arabic, Cyrillic, etc.)
    # Use strict word boundaries to prevent false matches

    # Check if first character is alphanumeric (Unicode-aware)
    if is_unicode_alnum(brand_name[0]):
        # For Unicode letters, use negative lookbehind for ASCII alphanumeric
        # and word characters from the same script
        left_boundary = r"(?<!\w)"
    else:
        # For special characters at start, use negative lookbehind for word character
        left_boundary = r"(?<!\w)"

    # Check if last character is alphanumeric (Unicode-aware)
    if is_unicode_alnum(brand_name[-1]):
        # For Unicode letters, use negative lookahead for ASCII alphanumeric
        # and word characters from the same script
        right_boundary = r"(?!\w)"
    else:
        # For special characters at end, use negative lookahead for word character
        right_boundary = r"(?!\w)"

    return left_boundary + escaped_name + right_boundary


def count_target_brand_mentions(
    raw_response: str, target_brand_names: list[str], proximity_threshold: int = 5
) -> int:
    """
    Count total occurrences of ALL target brand name variations in raw response,
    preventing double-counting of overlapping terms and nearby abbreviations.

    Uses case-sensitive word boundary matching with overlap detection:
    1. Sorts variations by length (longest first) to prioritize full names
    2. Claims character positions for each match PLUS a proximity buffer
    3. Skips subsequent matches that overlap with claimed positions

    This prevents counting both "AIMS Data Centre" and "AIMS" within the same phrase,
    and also prevents counting acronyms like "AIMS Data Centre (ACD)" as 2 mentions.

    Edge Case Handling:
    - Automatically generates space-removed variations (e.g., "Brand Name" → "BrandName")
    - This handles cases where brand names with spaces match their no-space variants

    Args:
        raw_response: The raw LLM response text
        target_brand_names: List of target brand name variations
        proximity_threshold: Number of characters after a match to consider as same mention (default: 5)

    Returns:
        Total count of non-overlapping target brand mentions

    Examples:
        # Case 1: Overlapping variations
        text = "AIMS Data Centre is great. AIMS offers service."
        brands = ["AIMS", "AIMS Data Centre"]
        Result: 2 mentions (not 3)
        - "AIMS Data Centre" at 0-16 → count (1)
        - "AIMS" at 0-4 → skip (overlaps)
        - "AIMS" at 27-31 → count (2)

        # Case 2: Acronym in parentheses (proximity detection)
        text = "AIMS Data Centre (ACD) is great."
        brands = ["AIMS", "AIMS Data Centre", "ACD"]
        Result: 1 mention (not 2)
        - "AIMS Data Centre" at 0-16 → count (1), claim 0-21 (16 + 5 buffer)
        - "AIMS" at 0-4 → skip (overlaps)
        - "ACD" at 18-21 → skip (overlaps with claimed positions 17-21)

        # Case 3: Space-removed variations
        text = "BrandName is great. Another Brand Name appears."
        brands = ["Brand Name"]
        Result: 2 mentions
        - "BrandName" at 0-9 → count (1) (matches space-removed variation)
        - "Brand Name" at 32-42 → count (2) (matches original)
    """
    if not raw_response or not target_brand_names:
        return 0

    # Generate expanded variations including space-removed versions
    expanded_variations = []
    seen_variations = set()  # Track unique variations to avoid duplicates

    for brand_name in target_brand_names:
        if not brand_name:
            continue

        # Add original brand name
        if brand_name not in seen_variations:
            expanded_variations.append(brand_name)
            seen_variations.add(brand_name)

        # Generate and add space-removed variation if brand contains spaces
        if " " in brand_name:
            space_removed = brand_name.replace(" ", "")
            if space_removed and space_removed not in seen_variations:
                expanded_variations.append(space_removed)
                seen_variations.add(space_removed)

    # Sort variations by length (longest first) to prioritize full names over abbreviations
    sorted_variations = sorted(expanded_variations, key=len, reverse=True)

    claimed_positions = set()
    total_count = 0

    for brand_name in sorted_variations:
        if not brand_name:  # Skip empty strings
            continue

        # Find all matches for this variation using smart word boundary pattern
        pattern = _build_smart_word_boundary_pattern(brand_name)

        for match in re.finditer(pattern, raw_response, re.IGNORECASE):
            match_start = match.start()
            match_end = match.end()

            # Check if this match overlaps with already claimed positions
            if any(pos in claimed_positions for pos in range(match_start, match_end)):
                continue

            # This is a new mention - count it
            total_count += 1

            # Claim this match's positions PLUS proximity buffer
            # This ensures nearby acronyms/abbreviations are not counted separately
            for pos in range(match_start, match_end + proximity_threshold):
                claimed_positions.add(pos)

    return total_count


def get_other_brands_count(other_brands_mentioned: list) -> int:
    """
    Get count of other brands mentioned.
    Simply returns the length of the other_brands_mentioned array.

    Args:
        other_brands_mentioned: List of other brands from LLM parsing

    Returns:
        Number of other brands mentioned
    """
    return len(other_brands_mentioned) if other_brands_mentioned else 0


def find_brand_first_position(raw_response: str, brand_names: list[str]) -> int | None:
    """
    Find the character position of the first occurrence of any brand name variant.
    Uses smart word boundary matching that handles special characters correctly.

    Edge Case Handling:
    - Automatically generates space-removed variations (e.g., "Brand Name" → "BrandName")
    - This ensures positions are correctly captured for both spaced and non-spaced variants

    Args:
        raw_response: The raw LLM response text
        brand_names: List of brand name variations to search for

    Returns:
        Character index of first occurrence, or None if not found
    """
    if not raw_response or not brand_names:
        return None

    # Generate expanded variations including space-removed versions
    expanded_variations = []
    seen_variations = set()

    for brand_name in brand_names:
        if not brand_name:
            continue

        # Add original brand name
        if brand_name not in seen_variations:
            expanded_variations.append(brand_name)
            seen_variations.add(brand_name)

        # Generate and add space-removed variation if brand contains spaces
        if " " in brand_name:
            space_removed = brand_name.replace(" ", "")
            if space_removed and space_removed not in seen_variations:
                expanded_variations.append(space_removed)
                seen_variations.add(space_removed)

    # Find first position across all variations
    first_pos = None
    for brand_name in expanded_variations:
        pattern = _build_smart_word_boundary_pattern(brand_name)
        match = re.search(pattern, raw_response, re.IGNORECASE)
        if match:
            pos = match.start()
            if first_pos is None or pos < first_pos:
                first_pos = pos

    return first_pos


def calculate_all_brand_positions(
    raw_response: str,
    target_brand_names: list[str],
    other_brands: list,
) -> dict:
    """
    Calculate ordinal positions for all brands based on order of first appearance.
    Position 1 = first brand to appear in text, Position 2 = second, etc.

    Args:
        raw_response: The raw LLM response text
        target_brand_names: List of target brand name variations
        other_brands: List of BrandMentionSchema objects for other brands

    Returns:
        Dict with:
            - target_position: Position of target brand (1-indexed) or None
            - other_positions: Dict mapping brand_name to position
            - all_positions: List of (brand_name, char_pos, is_target) sorted by char_pos
    """
    if not raw_response:
        return {
            "target_position": None,
            "other_positions": {},
            "all_positions": [],
        }

    # Collect all brands with their first character position
    brand_positions = []  # [(brand_name, char_pos, is_target)]

    # Find target brand position
    target_char_pos = find_brand_first_position(raw_response, target_brand_names)
    if target_char_pos is not None:
        # Use first target brand name as the representative name
        target_name = target_brand_names[0] if target_brand_names else "Target"
        brand_positions.append((target_name, target_char_pos, True))

    # Find other brand positions
    for brand in other_brands:
        brand_name = (
            brand.brand_name
            if hasattr(brand, "brand_name")
            else brand.get("brand_name", "")
        )
        if not brand_name:
            continue

        char_pos = find_brand_first_position(raw_response, [brand_name])
        if char_pos is not None:
            brand_positions.append((brand_name, char_pos, False))

    # Sort by character position (order of first appearance)
    brand_positions.sort(key=lambda x: x[1])

    # Assign ordinal positions (1-indexed)
    target_position = None
    other_positions = {}

    for ordinal_pos, (brand_name, _, is_target) in enumerate(brand_positions, start=1):
        if is_target:
            target_position = ordinal_pos
        else:
            other_positions[brand_name] = ordinal_pos

    return {
        "target_position": target_position,
        "other_positions": other_positions,
        "all_positions": brand_positions,
    }


def calculate_share_of_voice(
    target_mention_count: int, total_mentions_count: int
) -> float:
    """
    Calculate share of voice as a percentage.
    SOV = (target mentions / total mentions) * 100

    Args:
        target_mention_count: Number of target brand mentions
        total_mentions_count: Total mentions of ALL brands (target + competitors)

    Returns:
        Share of voice as percentage (0-100)
    """
    if total_mentions_count == 0:
        return 0.0

    return round((target_mention_count / total_mentions_count) * 100, 2)


def build_competitor_mentions(
    target_brand_names: list[str],
    target_mention_count: int,
    target_position: int | None,
    target_cited: bool,
    target_citation_text: str | None,
    other_brands: list,
    other_positions: dict,
    raw_response: str,
) -> list[dict]:
    """
    Build the competitor_mentions array for database storage.
    Includes both target brand and other brands.

    Args:
        target_brand_names: List of target brand name variations
        target_mention_count: Count of target brand mentions
        target_position: Position of target brand (1-indexed)
        target_cited: Whether target brand was cited
        target_citation_text: Citation text for target brand
        other_brands: List of other brands from LLM parsing
        other_positions: Dict mapping brand_name to position
        raw_response: Raw response text for counting other brand mentions

    Returns:
        List of competitor mention dicts for database
    """
    competitor_mentions = []

    # Add target brand first (if mentioned)
    if target_mention_count > 0:
        target_name = target_brand_names[0] if target_brand_names else "Your Brand"
        competitor_mentions.append(
            {
                "brand_name": target_name,
                "position": target_position,
                "mention_count": target_mention_count,
                "is_cited": target_cited,
                "citation_text": target_citation_text,
                "is_target_brand": True,
            }
        )

    # Add other brands
    for brand in other_brands:
        brand_name = (
            brand.brand_name
            if hasattr(brand, "brand_name")
            else brand.get("brand_name", "")
        )
        if not brand_name:
            continue

        # Count occurrences of this brand in raw text
        mention_count = count_brand_occurrences(
            raw_response, brand_name, use_word_boundary=True
        )

        # Get citation info
        citation_urls = (
            brand.citation_urls
            if hasattr(brand, "citation_urls")
            else brand.get("citation_urls", [])
        )
        citation_text = (
            brand.citation_text
            if hasattr(brand, "citation_text")
            else brand.get("citation_text")
        )
        is_cited = bool(citation_urls)

        competitor_mentions.append(
            {
                "brand_name": brand_name,
                "position": other_positions.get(brand_name),
                "mention_count": mention_count if mention_count > 0 else 1,
                "is_cited": is_cited,
                "citation_text": citation_text,
                "is_target_brand": False,
            }
        )

    return competitor_mentions


def build_citations_list(
    target_brand_names: list[str],
    target_brands: list,
    other_brands: list,
    positions: dict,
) -> list[dict]:
    """
    Build the citations array for database storage.
    Only includes brands that have citation URLs.

    Args:
        target_brand_names: List of target brand name variations
        target_brands: List of target brand mentions from LLM parsing
        other_brands: List of other brands from LLM parsing
        positions: Dict with target_position and other_positions

    Returns:
        List of citation dicts sorted by position
    """
    citations = []

    # Collect all cited brands
    cited_entries = []  # [(brand_name, citation_urls, is_target, position)]

    # Target brand citations
    for brand in target_brands:
        citation_urls = (
            brand.citation_urls
            if hasattr(brand, "citation_urls")
            else brand.get("citation_urls", [])
        )
        if citation_urls:
            target_name = target_brand_names[0] if target_brand_names else "Target"
            cited_entries.append(
                (target_name, citation_urls, True, positions.get("target_position"))
            )

    # Other brand citations
    for brand in other_brands:
        citation_urls = (
            brand.citation_urls
            if hasattr(brand, "citation_urls")
            else brand.get("citation_urls", [])
        )
        if citation_urls:
            brand_name = (
                brand.brand_name
                if hasattr(brand, "brand_name")
                else brand.get("brand_name", "")
            )
            position = positions.get("other_positions", {}).get(brand_name)
            cited_entries.append((brand_name, citation_urls, False, position))

    # Sort by position (order of first appearance)
    # Brands without position go last
    cited_entries.sort(key=lambda x: x[3] if x[3] is not None else 9999)

    # Build citation entries with citation_position (1-indexed order in citations list)
    for citation_position, (brand_name, citation_urls, is_target, _) in enumerate(
        cited_entries, start=1
    ):
        # Convert CitationUrlSchema objects to dicts for database storage
        citation_urls_list = []
        for url_obj in citation_urls:
            if isinstance(url_obj, dict):
                citation_urls_list.append(url_obj)
            elif hasattr(url_obj, "model_dump"):
                citation_urls_list.append(url_obj.model_dump())
            elif hasattr(url_obj, "url") and hasattr(url_obj, "source_type"):
                citation_urls_list.append({
                    "url": url_obj.url,
                    "source_type": url_obj.source_type
                })
            else:
                # Backward compatibility: plain string
                citation_urls_list.append({
                    "url": str(url_obj),
                    "source_type": "earned_media"
                })
        
        citations.append(
            {
                "brand_name": brand_name,
                "is_target_brand": is_target,
                "citation_count": len(citation_urls_list),
                "citation_urls": citation_urls_list,
                "citation_position": citation_position,
            }
        )

    return citations


def _derive_sentiment(parsed, target_brand_names: list[str]) -> str | None:
    """
    Derive legacy single sentiment string for target brand.

    Extracts sentiment_rating from brand_sentiments for the target brand.
    Maps: very positive/positive -> 'positive'; neutral -> 'neutral';
    negative/very negative -> 'negative'.
    """
    target_lower = {n.strip().lower() for n in target_brand_names if n}

    brand_sentiments = getattr(parsed, "brand_sentiments", None) or []
    for entry in brand_sentiments:
        name = getattr(entry, "brand_name", None)
        if not name or str(name).strip().lower() not in target_lower:
            continue
        
        # Get sentiment_rating directly from the new simplified schema
        rating = getattr(entry, "sentiment_rating", None)
        if not rating:
            return None
        
        r = str(rating).strip().lower()
        if r in ("very positive", "positive"):
            return "positive"
        if r == "neutral":
            return "neutral"
        if r in ("negative", "very negative"):
            return "negative"
        return None

    return None


def calculate_metrics(
    parsed,
    target_brand_names: list[str],
    raw_response: str,
) -> dict:
    """
    Calculate all metrics from parsed analysis and raw response.

    The LLM only identifies brands and citations. All metrics are calculated
    manually from the raw response text for consistency and accuracy:
    - Mention counts: String matching with word boundaries
    - Positions: Order of first appearance in text
    - Share of voice: target_count / total_count

    This mirrors the zicy-tools metrics calculator to ensure consistency
    between initial analysis and re-analysis.

    Args:
        parsed: Parsed analysis schema from Instructor (simplified)
        target_brand_names: List of target brand names
        raw_response: Raw LLM response text

    Returns:
        Dict with all calculated metrics
    """
    # Step 1: Count target brand mentions
    target_mention_count = count_target_brand_mentions(raw_response, target_brand_names)
    target_mentioned = target_mention_count > 0

    # Step 2: Get other brands count
    other_brands_count = get_other_brands_count(parsed.other_brands_mentioned)

    # Step 3: Calculate positions for all brands
    positions = calculate_all_brand_positions(
        raw_response=raw_response,
        target_brand_names=target_brand_names,
        other_brands=parsed.other_brands_mentioned,
    )
    target_position = positions["target_position"]
    other_positions = positions["other_positions"]

    # Step 4: Get target brand citation info
    target_cited = False
    target_citation_text = None
    if parsed.target_brand_mentions:
        first_target = parsed.target_brand_mentions[0]
        citation_urls = (
            first_target.citation_urls if hasattr(first_target, "citation_urls") else []
        )
        target_cited = bool(citation_urls)
        target_citation_text = (
            first_target.citation_text
            if hasattr(first_target, "citation_text")
            else None
        )

    # Step 5: Build competitor mentions list (needed for total_mentions_count)
    competitor_mentions = build_competitor_mentions(
        target_brand_names=target_brand_names,
        target_mention_count=target_mention_count,
        target_position=target_position,
        target_cited=target_cited,
        target_citation_text=target_citation_text,
        other_brands=parsed.other_brands_mentioned,
        other_positions=other_positions,
        raw_response=raw_response,
    )

    # Step 6: Calculate total mentions count (sum of all brand mentions)
    total_mentions_count = sum(brand["mention_count"] for brand in competitor_mentions)

    # Step 7: Calculate share of voice = target_mentions / total_mentions
    share_of_voice = calculate_share_of_voice(
        target_mention_count, total_mentions_count
    )

    # Step 8: Build citations list
    citations = build_citations_list(
        target_brand_names=target_brand_names,
        target_brands=parsed.target_brand_mentions,
        other_brands=parsed.other_brands_mentioned,
        positions=positions,
    )

    # Step 9: Get unique brands count
    unique_brands_count = (1 if target_mentioned else 0) + other_brands_count

    # Step 10: Derive sentiment (prefer multi-dimensional brand_sentiments for target brand)
    sentiment = _derive_sentiment(parsed, target_brand_names)

    # Step 11: Serialize brand_sentiments for DB (list of dicts)
    brand_sentiments_raw = getattr(parsed, "brand_sentiments", None) or []
    brand_sentiments = [
        bs.model_dump() if hasattr(bs, "model_dump") else bs
        for bs in brand_sentiments_raw
    ]

    # Step 11b: Serialize key_topics for DB (list of dicts)
    key_topics_raw = getattr(parsed, "key_topics", None) or []
    key_topics = [
        kt.model_dump() if hasattr(kt, "model_dump") else kt
        for kt in key_topics_raw
    ]

    # Step 12: Return final metrics dict (SOV now correctly uses total_mentions_count)
    return {
        "target_brand_mentioned": target_mentioned,
        "target_brand_position": target_position,
        "target_brand_mention_count": target_mention_count,
        "target_brand_cited": target_cited,
        "target_brand_citation_text": target_citation_text,
        "competitor_mentions": competitor_mentions,
        "citations": citations,
        "unique_brands_count": unique_brands_count,
        "total_mentions_count": total_mentions_count,
        "share_of_voice": share_of_voice,
        "sentiment": sentiment,
        "brand_sentiments": brand_sentiments,
        "key_topics": key_topics,
        "response_type": parsed.response_type,
    }


def build_analysis_document(
    raw_response: str,
    metrics: dict,
    analysis_duration_seconds: float,
) -> dict:
    """
    Build the complete document structure for MongoDB update.
    Returns the $set payload ready for database update.

    Args:
        raw_response: The raw LLM response text
        metrics: Calculated metrics from calculate_metrics()
        analysis_duration_seconds: Time taken for analysis

    Returns:
        Dict with all fields ready for MongoDB $set operation
    """
    return {
        "raw_response": raw_response,
        "target_brand_mentioned": metrics["target_brand_mentioned"],
        "target_brand_position": metrics["target_brand_position"],
        "target_brand_mention_count": metrics["target_brand_mention_count"],
        "target_brand_cited": metrics["target_brand_cited"],
        "target_brand_citation_text": metrics["target_brand_citation_text"],
        "competitor_mentions": metrics["competitor_mentions"],
        "citations": metrics.get("citations", []),
        "unique_brands_count": metrics["unique_brands_count"],
        "total_mentions_count": metrics["total_mentions_count"],
        "share_of_voice": metrics["share_of_voice"],
        "sentiment": metrics["sentiment"],
        "brand_sentiments": metrics.get("brand_sentiments", []),
        "key_topics": metrics.get("key_topics", []),
        "response_quality": metrics.get("response_type"),
        "analysis_status": "analysed",
        "analysis_error": None,
        "analysis_duration_seconds": analysis_duration_seconds,
        "analyzed_at": datetime.now(timezone.utc),
    }
