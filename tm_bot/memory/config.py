"""
Memory module configuration (env and paths).

All memory-related env vars are read here; no other code should read them directly.
Memory is per-user: get_memory_root(root_dir, user_id) returns that user's directory.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Union


def is_memory_configured() -> bool:
    """True when a memory/vector backend URL is configured."""
    url = get_memory_vector_db_url()
    return bool(url)


def get_memory_vector_db_url() -> str:
    """
    Resolve vector DB URL for memory search.
    Prefer memory-specific env, then fall back to shared Qdrant URL.
    """
    return (
        os.getenv("MEMORY_VECTOR_DB_URL", "").strip()
        or os.getenv("QDRANT_URL", "").strip()
    )


def get_memory_vector_db_api_key() -> str:
    """Resolve memory/vector API key, preferring memory-specific env."""
    return (
        os.getenv("MEMORY_VECTOR_DB_API_KEY", "").strip()
        or os.getenv("QDRANT_API_KEY", "").strip()
    )


def get_memory_collection_name() -> str:
    """Qdrant collection name used for conversational memory chunks."""
    return (
        os.getenv("MEMORY_VECTOR_COLLECTION", "").strip()
        or os.getenv("MEMORY_QDRANT_COLLECTION", "").strip()
        or "user_memory_v1"
    )


def get_memory_embedding_model() -> str:
    """Embedding model for memory search/indexing."""
    return (
        os.getenv("MEMORY_EMBEDDING_MODEL", "").strip()
        or os.getenv("VERTEX_EMBEDDING_MODEL", "").strip()
        or "gemini-embedding-001"
    )


def is_flush_enabled() -> bool:
    """True when pre-compaction flush is enabled (writes to memory/YYYY-MM-DD.md)."""
    if os.getenv("MEMORY_FLUSH_ENABLED", "").strip().lower() in ("1", "true", "yes"):
        return True
    return is_memory_configured()


def get_memory_root(root_dir: Union[str, Path], user_id: str) -> Path:
    """
    Per-user memory root. Each user has isolated MEMORY.md and memory/ directory.

    Convention: root_dir/<user_id>/ so paths are e.g.:
      root_dir/12345/MEMORY.md
      root_dir/12345/memory/2025-02-19.md
    """
    root = Path(root_dir).resolve()
    user_str = str(user_id).strip()
    if not user_str or ".." in user_str or "/" in user_str or "\\" in user_str:
        raise ValueError("Invalid user_id for memory path")
    return root / user_str
