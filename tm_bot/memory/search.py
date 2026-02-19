"""
Semantic memory search. Returns disabled when no vector DB is configured.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from memory.config import get_memory_root, is_memory_configured


def memory_search(
    query: str,
    root_dir: str,
    user_id: str,
    max_results: Optional[int] = None,
    min_score: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Semantically search this user's MEMORY.md and memory/*.md.

    When MEMORY_VECTOR_DB_URL is not set, returns disabled payload.
    When set (later), call vector backend scoped to user_id and return OpenClaw-like results.
    """
    if not is_memory_configured():
        return {
            "results": [],
            "disabled": True,
            "error": "Memory not configured. Set MEMORY_VECTOR_DB_URL to enable semantic search.",
        }
    # Placeholder for future vector backend integration (per-user index/namespace).
    _ = get_memory_root(root_dir, user_id), max_results, min_score, query
    return {
        "results": [],
        "disabled": False,
        "error": None,
    }
