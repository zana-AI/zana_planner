"""
Web tools for the LLM agent: web_search (Brave API) and web_fetch (URL content extraction).
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests

from services.learning_pipeline.constants import DEFAULT_FETCH_TIMEOUT_SECONDS
from services.learning_pipeline.ingestors.common import safe_get
from services.learning_pipeline.security import validate_safe_http_url
from utils.logger import get_logger

logger = get_logger(__name__)

# In-memory cache for web_search: key = (query, count, freshness), value = (result, expiry_ts)
_SEARCH_CACHE: Dict[tuple, tuple] = {}
_SEARCH_CACHE_TTL_SECONDS = 900  # 15 min

WEB_FETCH_MAX_CHARS_DEFAULT = 5000
WEB_FETCH_MAX_CHARS_CAP = 15000
BRAVE_SEARCH_URL = "https://api.brave.com/res/v1/web/search"

try:
    import trafilatura
except Exception:
    trafilatura = None

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None


def web_search(
    query: str,
    count: Optional[int] = None,
    freshness: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Search the web using Brave Search API.
    Returns list of {title, url, snippet, age} or {disabled, error} if not configured.
    """
    query = (query or "").strip()
    if not query:
        return {"results": [], "error": "query is required"}
    count = max(1, min(5, count or 3))
    api_key = (os.getenv("BRAVE_SEARCH_API_KEY") or os.getenv("BRAVE_API_KEY") or "").strip()
    if not api_key:
        return {
            "results": [],
            "disabled": True,
            "error": "BRAVE_SEARCH_API_KEY (or BRAVE_API_KEY) not set. Configure to enable web search.",
        }
    cache_key = (query, count, freshness or "")
    if cache_key in _SEARCH_CACHE:
        cached_result, expiry = _SEARCH_CACHE[cache_key]
        if time.time() < expiry:
            return cached_result
        del _SEARCH_CACHE[cache_key]

    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": api_key,
    }
    params: Dict[str, Any] = {"q": query, "count": count}
    if freshness:
        params["freshness"] = freshness  # pd, pw, pm, py

    try:
        resp = requests.get(
            BRAVE_SEARCH_URL,
            params=params,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.warning("Brave search request failed: %s", e)
        return {"results": [], "error": str(e)}

    results: List[Dict[str, Any]] = []
    web = data.get("web") or {}
    for r in (web.get("results") or [])[:count]:
        results.append({
            "title": (r.get("title") or "").strip(),
            "url": (r.get("url") or "").strip(),
            "snippet": (r.get("description") or "").strip(),
            "age": (r.get("age") or "").strip(),
        })
    out = {"results": results}
    _SEARCH_CACHE[cache_key] = (out, time.time() + _SEARCH_CACHE_TTL_SECONDS)
    return out


def web_fetch(
    url: str,
    max_chars: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Fetch and extract readable content from a URL.
    Uses trafilatura with BeautifulSoup fallback. Respects SSRF (safe URLs only).
    """
    url = (url or "").strip()
    if not url:
        return {"url": "", "title": "", "content": "", "error": "url is required"}
    try:
        validate_safe_http_url(url)
    except ValueError as e:
        return {"url": url, "title": "", "content": "", "error": str(e)}

    max_chars = max(0, min(WEB_FETCH_MAX_CHARS_CAP, max_chars or WEB_FETCH_MAX_CHARS_DEFAULT))

    try:
        response = safe_get(url, timeout_seconds=DEFAULT_FETCH_TIMEOUT_SECONDS)
        response.raise_for_status()
        html = response.text[: max_chars * 3]
        if trafilatura is not None:
            extracted = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=False,
                include_images=False,
                include_links=False,
            )
            if extracted:
                truncated = len(extracted) > max_chars
                content = extracted[:max_chars]
                metadata = trafilatura.extract_metadata(html)
                title = (getattr(metadata, "title", None) or "") if metadata else ""
                return {
                    "url": url,
                    "title": (title or "").strip(),
                    "content": content,
                    "char_count": len(content),
                    "truncated": truncated,
                }
        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "noscript", "iframe"]):
                tag.decompose()
            title_tag = soup.find("meta", property="og:title") or soup.find("title")
            title = ""
            if title_tag:
                title = title_tag.get("content") if title_tag.name == "meta" else (title_tag.get_text(strip=True) or "")
            body = soup.find("article") or soup.body or soup
            text = body.get_text(separator="\n", strip=True) if body else ""
        else:
            title = ""
            text = html[:max_chars]
        truncated = len(text) > max_chars
        content = text[:max_chars]
        return {
            "url": url,
            "title": (title or "").strip(),
            "content": content,
            "char_count": len(content),
            "truncated": truncated,
        }
    except Exception as e:
        logger.warning("web_fetch failed for %s: %s", url, e)
        return {"url": url, "title": "", "content": "", "error": str(e)}
