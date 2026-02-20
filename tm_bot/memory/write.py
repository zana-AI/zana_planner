"""
Write durable memories to per-user memory files.

This gives the LLM a tool to persist important facts, preferences, decisions,
and context during *any* conversation — not only near context-window compaction.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union

from memory.config import get_memory_root

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 4000


def memory_write(
    text: str,
    root_dir: Union[str, Path],
    user_id: str,
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Append *text* to this user's ``memory/YYYY-MM-DD.md``.

    Creates the ``memory/`` directory and date file if they don't exist.
    Each entry is separated by a horizontal rule so the file stays scannable.
    Returns a dict with ``ok``, ``path``, and optionally ``error``.
    """
    if not text or not text.strip():
        return {"ok": False, "path": "", "error": "text is empty"}
    stripped = text.strip()
    if len(stripped) > MAX_TEXT_LENGTH:
        stripped = stripped[:MAX_TEXT_LENGTH]

    try:
        root = get_memory_root(root_dir, user_id)
    except ValueError as e:
        return {"ok": False, "path": "", "error": str(e)}

    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    date_stamp = now_utc.strftime("%Y-%m-%d")

    memory_dir = root / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    target = memory_dir / f"{date_stamp}.md"
    rel_path = f"memory/{date_stamp}.md"

    block = f"\n\n---\n\n{stripped}\n"
    try:
        existing = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
        target.write_text(existing + block, encoding="utf-8")
    except OSError as e:
        logger.warning("memory_write failed for user %s: %s", user_id, e)
        return {"ok": False, "path": rel_path, "error": str(e)}

    logger.info("memory_write: appended %d chars for user %s → %s", len(stripped), user_id, rel_path)
    return {"ok": True, "path": rel_path}
