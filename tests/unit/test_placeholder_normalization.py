"""
Unit tests for the placeholder normalization helpers in llms/agent.py.

Covers _is_from_search and _parse_from_tool with the case/whitespace variants
that Gemini Flash is known to generate.
"""
import re
from typing import Optional

import pytest

# ---------------------------------------------------------------------------
# Inline copies of the helpers under test.
# These mirror the definitions in tm_bot/llms/agent.py exactly so that the
# tests remain runnable without importing langgraph/langchain.
# ---------------------------------------------------------------------------

_FROM_SEARCH_RE = re.compile(r"^from[_\s]?search", re.IGNORECASE)
_FROM_TOOL_RE = re.compile(r"^from[_\s]?tool\s*:\s*([^:]*?)\s*:\s*(.*)", re.IGNORECASE)


def _is_from_search(val: str) -> bool:
    return bool(_FROM_SEARCH_RE.match(val or ""))


def _parse_from_tool(val: str) -> Optional[tuple]:
    m = _FROM_TOOL_RE.match(val or "")
    if not m:
        return None
    return m.group(1).strip(), m.group(2).strip()


class TestIsFromSearch:
    """_is_from_search should accept all reasonable LLM-generated variants."""

    @pytest.mark.parametrize("val", [
        "FROM_SEARCH",          # canonical form
        "from_search",          # all lower
        "From_Search",          # mixed case
        "FROM SEARCH",          # space instead of underscore
        "from search",          # lower + space
        "FROM_SEARCH_RESULT",   # extra suffix — starts with from_search
    ])
    def test_truthy_variants(self, val):
        assert _is_from_search(val), f"Expected truthy for {val!r}"

    @pytest.mark.parametrize("val", [
        "FROM_TOOL:resolve_datetime:",
        "P10",
        "promise_id",
        "",
        "SEARCH_FROM",          # reversed — not a valid placeholder
    ])
    def test_falsy_variants(self, val):
        assert not _is_from_search(val), f"Expected falsy for {val!r}"


class TestParseFromTool:
    """_parse_from_tool should handle case/whitespace variants."""

    def test_canonical_form(self):
        result = _parse_from_tool("FROM_TOOL:resolve_datetime:")
        assert result == ("resolve_datetime", "")

    def test_canonical_with_field(self):
        result = _parse_from_tool("FROM_TOOL:search_promises:promise_id")
        assert result == ("search_promises", "promise_id")

    def test_lowercase(self):
        result = _parse_from_tool("from_tool:resolve_datetime:")
        assert result == ("resolve_datetime", "")

    def test_extra_spaces_around_tool_name(self):
        result = _parse_from_tool("FROM_TOOL: resolve_datetime :")
        assert result == ("resolve_datetime", "")

    def test_space_as_separator(self):
        result = _parse_from_tool("FROM TOOL:resolve_datetime:iso_date")
        assert result == ("resolve_datetime", "iso_date")

    def test_non_matching_returns_none(self):
        assert _parse_from_tool("FROM_SEARCH") is None
        assert _parse_from_tool("P10") is None
        assert _parse_from_tool("") is None
        assert _parse_from_tool("random_value") is None
