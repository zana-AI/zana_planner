"""
Memory module: semantic memory tools (memory_search, memory_get) and pre-compaction flush.

Inspired by OpenClaw. When MEMORY_VECTOR_DB_URL is not set, memory_search returns disabled;
memory_get reads from per-user files; flush can be gated by MEMORY_FLUSH_ENABLED.
"""

from memory.config import (
    get_memory_root,
    is_flush_enabled,
    is_memory_configured,
)
from memory.read import memory_get
from memory.search import memory_search
from memory.flush import (
    resolve_memory_flush_prompt,
    run_memory_flush,
    should_run_memory_flush,
)

__all__ = [
    "get_memory_root",
    "is_flush_enabled",
    "is_memory_configured",
    "memory_get",
    "memory_search",
    "resolve_memory_flush_prompt",
    "run_memory_flush",
    "should_run_memory_flush",
]
