"""Analytics built from the BRAND-CENTRIC structure (POC).

The point of this module is to show how much simpler analytics become when
every brand's data already lives together. We reuse the EXISTING
`services.metrics_calculator` for the deterministic raw-text math (mention
counts, ordinal positions, share of voice) so the comparison isolates the
*structure*, not the arithmetic.

The headline win: building a per-brand "card" (mention count + position +
citation source breakdown + sentiment) needs NO name-matching across lists,
because the brand object already carries all of it. Contrast this with the
current design, where sentiment lives in a separate `brand_sentiments` list
that must be fuzzy-joined back to the mention rows by brand name.
"""

import services.metrics_calculator as mc
from poc.brand_centric_schema import AEOBrandCentricSchema


def _empty_breakdown() -> dict:
    return {"owned_media": 0, "earned_media": 0, "competitor": 0, "other": 0}


def build_brand_centric_analytics(
    parsed: AEOBrandCentricSchema,
    target_brand_names: list[str],
    raw_response: str,
) -> dict:
    """Compute analytics directly from the brand-centric parse.

    Returns a dict with a self-contained per-brand card list plus target /
    citation / topic rollups.
    """
    # NOTE: the cron-server metrics_calculator computes everything from the raw
    # text directly (it does not URL-mask like the zicy-tools copy does), so we
    # use raw_response here too to keep the comparison apples-to-apples.
    target_mention_count = mc.count_target_brand_mentions(raw_response, target_brand_names)
    target_mentioned = target_mention_count > 0

    non_target_dicts = [
        {"brand_name": b.brand_name} for b in parsed.brands if not b.is_target
    ]
    positions = mc.calculate_all_brand_positions(
        raw_response=raw_response,
        target_brand_names=target_brand_names,
        other_brands=non_target_dicts,
    )

    brand_cards: list[dict] = []
    citation_breakdown_total = _empty_breakdown()
    citations_total = 0

    for b in parsed.brands:
        # mention count + position straight from raw text
        if b.is_target:
            mention_count = target_mention_count
            position = positions["target_position"]
        else:
            mention_count = mc.count_brand_occurrences(raw_response, b.brand_name) or 1
            position = positions["other_positions"].get(b.brand_name)

        # citation source breakdown — trivial, the URLs live on the brand
        breakdown = _empty_breakdown()
        for c in b.citation_urls:
            st = (c.source_type or "other").lower()
            if st not in breakdown:
                st = "other"
            breakdown[st] += 1
            citation_breakdown_total[st] += 1
        citations_total += len(b.citation_urls)

        brand_cards.append(
            {
                "brand_name": b.brand_name,
                "is_target": b.is_target,
                "mention_count": mention_count,
                "position": position,
                "is_cited": bool(b.citation_urls),
                "citation_count": len(b.citation_urls),
                "citation_source_breakdown": breakdown,
                # sentiment is RIGHT HERE on the same object — no join needed
                "sentiment_score": b.sentiment_score,
                "sentiment_rating": b.sentiment_rating,
                "sentiment_descriptor_count": len(b.sentiment_descriptors),
            }
        )

    # sort cards by mention count desc (typical dashboard ordering)
    brand_cards.sort(key=lambda c: c["mention_count"], reverse=True)

    total_mentions = sum(c["mention_count"] for c in brand_cards)
    share_of_voice = mc.calculate_share_of_voice(target_mention_count, total_mentions)

    target_card = next((c for c in brand_cards if c["is_target"]), None)

    return {
        "response_type": parsed.response_type,
        "brand_count": len(brand_cards),
        "target": {
            "mentioned": target_mentioned,
            "mention_count": target_mention_count,
            "position": positions["target_position"],
            "cited": bool(target_card and target_card["is_cited"]),
            "sentiment_rating": target_card["sentiment_rating"] if target_card else None,
            "share_of_voice": share_of_voice,
        },
        "total_mentions_count": total_mentions,
        "share_of_voice": share_of_voice,
        "citations_total": citations_total,
        "citation_source_breakdown": citation_breakdown_total,
        "brand_cards": brand_cards,
        "key_topics": [kt.model_dump() for kt in parsed.key_topics],
    }


def old_sentiment_join_report(old_parsed) -> dict:
    """Quantify the fragility of the CURRENT 4-list design.

    For each entry in `brand_sentiments`, check whether its brand_name matches
    (case-insensitive, exact) any brand from the mention lists. Anything that
    fails to match exactly would require fuzzy/heuristic joining downstream
    (which is what the analytics service actually does today).
    """
    mention_names = set()
    for b in getattr(old_parsed, "target_brand_mentions", []) or []:
        if getattr(b, "brand_name", None):
            mention_names.add(b.brand_name.strip().lower())
    for b in getattr(old_parsed, "other_brands_mentioned", []) or []:
        if getattr(b, "brand_name", None):
            mention_names.add(b.brand_name.strip().lower())

    sentiments = getattr(old_parsed, "brand_sentiments", []) or []
    matched, unmatched_names = 0, []
    for s in sentiments:
        name = (getattr(s, "brand_name", "") or "").strip().lower()
        if name and name in mention_names:
            matched += 1
        else:
            unmatched_names.append(getattr(s, "brand_name", ""))

    total = len(sentiments)
    return {
        "sentiment_entries": total,
        "exact_matched_to_mention": matched,
        "needs_fuzzy_join": len(unmatched_names),
        "unmatched_sentiment_brands": unmatched_names,
        "fragile": len(unmatched_names) > 0,
    }
