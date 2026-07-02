"""Helper functions for URL filtering in AEO analysis.

MIRRORS zicy-tools url_filters to ensure consistency.
"""


def should_filter_url(url: str) -> bool:
    """
    Determine if a URL should be filtered out from citations.

    Filters out:
    - Google image/maps/search URLs
    - DataForSEO URLs
    - Other non-website URLs

    Args:
        url: The URL to check

    Returns:
        bool: True if URL should be filtered out, False if it should be kept
    """
    if not url:
        return True

    # Convert to lowercase for case-insensitive matching
    url_lower = url.lower()

    # Filter patterns
    filter_patterns = [
        "images.google.com",
        "maps.google.com",
        "google.com/search",
        "dataforseo.com",
        "www.google.com/search",
        "google.com/url",
    ]

    # Check if URL contains any filter pattern
    for pattern in filter_patterns:
        if pattern in url_lower:
            return True

    return False
