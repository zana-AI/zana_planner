"""
URL utilities for content manager: canonicalization for deduplication.
"""
import re
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

# Query parameter names to strip (tracking / campaign params)
_TRACKING_PARAMS = frozenset({
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'fbclid', 'gclid', 'gclsrc', 'dclid', 'ref', 'referrer', 'mc_cid', 'mc_eid',
    '_ga', '_gl', 'msclkid', 'twclid', 'li_fat_id', 'otc', 'vero_id',
})


def canonicalize_url(url: str) -> str:
    """
    Normalize a URL for deduplication: strip tracking params, lowercase scheme/host,
    remove trailing slashes, sort remaining query params.

    Args:
        url: Raw URL string.

    Returns:
        Canonical URL string.
    """
    if not url or not url.strip():
        return url.strip() if url else ''
    s = url.strip()
    try:
        parsed = urlparse(s)
    except Exception:
        return s
    # Normalize scheme and netloc to lowercase
    scheme = (parsed.scheme or 'https').lower()
    netloc = (parsed.netloc or '').lower()
    path = parsed.path or '/'
    # Remove trailing slash from path (except for root)
    if len(path) > 1 and path.endswith('/'):
        path = path.rstrip('/')
    # Filter and sort query params
    query_dict = parse_qs(parsed.query, keep_blank_values=False)
    filtered = {
        k: v for k, v in query_dict.items()
        if k.lower() not in _TRACKING_PARAMS
    }
    query = urlencode(sorted(filtered.items()), doseq=True) if filtered else ''
    fragment = parsed.fragment or ''
    return urlunparse((scheme, netloc, path, parsed.params, query, fragment))
