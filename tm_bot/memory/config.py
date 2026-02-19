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
    """True when MEMORY_VECTOR_DB_URL is set (vector backend will be used for search)."""
    url = os.getenv("MEMORY_VECTOR_DB_URL", "").strip()
    return bool(url)


def is_flush_enabled() -> bool:
    """True when pre-compaction flush is enabled (writes to memory/YYYY-MM-DD.md)."""
    if os.getenv("MEMORY_FLUSH_ENABLED", "").strip().lower() in ("1", "true", "yes"):
        return True
    return is_memory_configured()


def get_memory_root(root_dir: Union[str, Path], user_id: str) -> Path:
    """
    Per-user memory root. Each user has isolated MEMORY.md and memory/ directory.

    Convention: root_dir/users/<user_id>/ so paths are e.g.:
      root_dir/users/12345/MEMORY.md
      root_dir/users/12345/memory/2025-02-19.md
    """
    root = Path(root_dir).resolve()
    user_str = str(user_id).strip()
    if not user_str or ".." in user_str or "/" in user_str or "\\" in user_str:
        raise ValueError("Invalid user_id for memory path")
    return root / "users" / user_str
