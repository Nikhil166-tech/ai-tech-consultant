import urllib.parse
import re
from typing import Tuple, Optional, Set

TRACKING_QUERY_PARAMS: Set[str] = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    "gclid", "fbclid", "msclkid", "ref", "mc_cid", "mc_eid"
}

def canonicalize_url(url: str, is_sitemap: bool = False) -> str:
    """
    Carefully canonicalizes URLs to ensure deduplication across registrations and crawls:
    1. Lowercase scheme and host.
    2. Strip default ports (80 for http, 443 for https).
    3. Strip URL fragments (#...).
    4. Strip marketing/tracking query parameters (utm_*, gclid, fbclid, etc.) while
       strictly preserving functional parameters (e.g., page, id, lang, format).
    5. Sort functional query parameters for deterministic equivalence.
    6. Normalize duplicate slashes in path (e.g., //sitemap.xml -> /sitemap.xml).
    7. Normalize trailing slashes:
       - Root domain always has trailing slash: https://example.com/
       - File paths (.xml, .html, .php, etc.) never have trailing slash: /sitemap.xml
       - Directory paths without extension have consistent trailing slash or no trailing slash.
    """
    if not url or not isinstance(url, str):
        return ""

    url = url.strip()
    parsed = urllib.parse.urlsplit(url)

    # 1. Scheme
    scheme = parsed.scheme.lower()
    if not scheme:
        scheme = "https"

    # 2. Hostname & Port
    netloc = parsed.netloc.lower()
    if "@" in netloc:
        auth_part, host_port = netloc.split("@", 1)
        netloc = f"{auth_part}@{host_port}"
    else:
        host_port = netloc

    if ":" in host_port:
        host, port_str = host_port.split(":", 1)
        try:
            port = int(port_str)
            if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
                netloc = host
            else:
                netloc = f"{host}:{port}"
        except ValueError:
            pass

    # 3. Path normalization
    path = parsed.path
    if not path:
        path = "/"
    else:
        # Collapse multiple consecutive slashes
        path = re.sub(r"/+", "/", path)

        # File-like extensions should not have trailing slashes
        if is_sitemap or re.search(r"\.(xml|gz|html|htm|php|json|pdf|txt)/?$", path, re.I):
            path = path.rstrip("/")
        elif path != "/" and path.endswith("/"):
            # Normalize trailing slash for folder paths to no trailing slash for consistency
            path = path.rstrip("/")

    # 4. Query parameters
    cleaned_query_parts = []
    if parsed.query:
        query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        # Filter out tracking params
        kept_pairs = [
            (k, v) for k, v in query_pairs
            if k.lower() not in TRACKING_QUERY_PARAMS and not k.lower().startswith("utm_")
        ]
        # Sort for determinism
        kept_pairs.sort(key=lambda x: (x[0], x[1]))
        if kept_pairs:
            cleaned_query_parts = urllib.parse.urlencode(kept_pairs)
        else:
            cleaned_query_parts = ""
    else:
        cleaned_query_parts = ""

    # 5. Recombine without fragment
    return urllib.parse.urlunsplit((scheme, netloc, path, cleaned_query_parts, ""))


def extract_url_domain(url: str) -> str:
    """Extracts lowercase domain name without port or auth."""
    try:
        parsed = urllib.parse.urlsplit(url)
        host = parsed.hostname or ""
        return host.lower()
    except Exception:
        return ""
