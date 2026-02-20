"""
Unit tests for web_tools: web_search and web_fetch.
"""

from unittest.mock import MagicMock, patch

import pytest

from services.web_tools import web_search, web_fetch


@pytest.mark.unit
def test_web_search_disabled_without_api_key(monkeypatch):
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    out = web_search("hello")
    assert out.get("disabled") is True
    assert "BRAVE" in (out.get("error") or "")
    assert out.get("results") == []


@pytest.mark.unit
def test_web_search_returns_results(monkeypatch):
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test-key")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "web": {
            "results": [
                {"title": "Example", "url": "https://example.com", "description": "Snippet here", "age": ""},
            ]
        },
    }
    with patch("services.web_tools.requests.get", return_value=mock_resp):
        out = web_search("test query", count=2)
    assert out.get("disabled") is None or out.get("disabled") is False
    assert "results" in out
    assert len(out["results"]) >= 1
    assert out["results"][0]["title"] == "Example"
    assert out["results"][0]["url"] == "https://example.com"
    assert out["results"][0]["snippet"] == "Snippet here"


@pytest.mark.unit
def test_web_search_cache_hit(monkeypatch):
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test-key")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "web": {"results": [{"title": "Cached", "url": "https://cached.com", "description": "Cached snippet", "age": ""}]},
    }
    with patch("services.web_tools.requests.get", return_value=mock_resp) as mock_get:
        out1 = web_search("cache me")
        out2 = web_search("cache me")
    assert out1["results"][0]["title"] == "Cached"
    assert out2["results"][0]["title"] == "Cached"
    assert mock_get.call_count == 1


@pytest.mark.unit
def test_web_search_empty_query():
    out = web_search("")
    assert "error" in out
    assert out.get("results") == []


@pytest.mark.unit
def test_web_fetch_extracts_content():
    url = "https://example.com/article"
    html = """
    <html><head><title>Test Page</title><meta property="og:title" content="OG Title" /></head>
    <body><article><h1>Hello</h1><p>This is the main content.</p></article></body></html>
    """
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.text = html
    with patch("services.web_tools.safe_get", return_value=mock_resp):
        out = web_fetch(url, max_chars=5000)
    assert "error" not in out or not out.get("error")
    assert out.get("url") == url
    assert out.get("char_count", 0) > 0
    assert "content" in out


@pytest.mark.unit
def test_web_fetch_truncates_long_content():
    url = "https://example.com/long"
    long_text = "x" * 20000
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.text = f"<html><body><p>{long_text}</p></body></html>"
    with patch("services.web_tools.safe_get", return_value=mock_resp):
        out = web_fetch(url, max_chars=1000)
    assert out.get("char_count", 0) <= 1000
    assert out.get("truncated") is True


@pytest.mark.unit
def test_web_fetch_rejects_private_urls():
    out = web_fetch("http://localhost/page")
    assert "error" in out
    assert "content" in out
    assert out.get("content") == ""


@pytest.mark.unit
def test_web_fetch_empty_url():
    out = web_fetch("")
    assert "error" in out
    assert out.get("url") == ""
