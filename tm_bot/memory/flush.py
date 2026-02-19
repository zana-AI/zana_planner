"""
Pre-compaction memory flush: persist durable memories to disk before context is compacted.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

from memory.config import get_memory_root, is_flush_enabled

SILENT_REPLY_TOKEN = "<silent>"
DEFAULT_MEMORY_FLUSH_SOFT_TOKENS = 4000
DEFAULT_RESERVE_TOKENS_FLOOR = 2048
DEFAULT_CONTEXT_WINDOW_TOKENS = 128000

DEFAULT_MEMORY_FLUSH_PROMPT = (
    "Pre-compaction memory flush. "
    "Store durable memories now (use memory/YYYY-MM-DD.md; create memory/ if needed). "
    "IMPORTANT: If the file already exists, APPEND new content only and do not overwrite existing entries. "
    f"If nothing to store, reply with {SILENT_REPLY_TOKEN}."
)

DEFAULT_MEMORY_FLUSH_SYSTEM_PROMPT = (
    "Pre-compaction memory flush turn. "
    "The session is near auto-compaction; capture durable memories to disk. "
    f"You may reply, but usually {SILENT_REPLY_TOKEN} is correct."
)


def _format_date_stamp(now_utc: Optional[datetime] = None) -> str:
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    return now_utc.strftime("%Y-%m-%d")


def resolve_memory_flush_prompt(
    now_utc: Optional[datetime] = None,
    prompt_template: str = DEFAULT_MEMORY_FLUSH_PROMPT,
) -> str:
    """Return the flush user prompt with YYYY-MM-DD replaced by the current date."""
    date_stamp = _format_date_stamp(now_utc)
    return prompt_template.replace("YYYY-MM-DD", date_stamp).strip()


def resolve_memory_flush_system_prompt() -> str:
    """Return the flush system prompt (with silent-reply hint if not already present)."""
    text = DEFAULT_MEMORY_FLUSH_SYSTEM_PROMPT
    if SILENT_REPLY_TOKEN not in text:
        text = f"{text}\n\nIf no user-visible reply is needed, start with {SILENT_REPLY_TOKEN}."
    return text


def should_run_memory_flush(
    entry: Optional[Dict[str, Any]] = None,
    context_window_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS,
    reserve_tokens_floor: int = DEFAULT_RESERVE_TOKENS_FLOOR,
    soft_threshold_tokens: int = DEFAULT_MEMORY_FLUSH_SOFT_TOKENS,
) -> bool:
    """
    True when we should run a flush turn (session near limit and not already flushed this compaction).

    entry can provide:
      - total_tokens or estimated_tokens (preferred)
      - message_count (proxy when token count not available)
      - compaction_count, memory_flush_compaction_count (to avoid double flush)

    When token count is missing, we use message_count as a proxy: if message_count >= 50 (e.g.),
    treat as "over threshold". Tune the threshold for turn-count proxy as needed.
    """
    total_tokens = 0
    if entry:
        total_tokens = entry.get("total_tokens") or entry.get("estimated_tokens") or 0
        if total_tokens <= 0 and entry.get("message_count") is not None:
            msg_count = int(entry.get("message_count", 0))
            if msg_count >= 50:
                total_tokens = context_window_tokens - reserve_tokens_floor - soft_threshold_tokens
    if total_tokens <= 0:
        return False
    context_window = max(1, context_window_tokens)
    reserve = max(0, reserve_tokens_floor)
    soft = max(0, soft_threshold_tokens)
    threshold = max(0, context_window - reserve - soft)
    if threshold <= 0 or total_tokens < threshold:
        return False
    compaction_count = (entry or {}).get("compaction_count", 0)
    last_flush_at = (entry or {}).get("memory_flush_compaction_count")
    if last_flush_at is not None and last_flush_at == compaction_count:
        return False
    return True


def run_memory_flush(
    root_dir: Union[str, Path],
    user_id: str,
    run_flush_llm: Callable[[str, str], str],
    now_utc: Optional[datetime] = None,
) -> None:
    """
    Run one LLM turn with flush prompt and append the model reply to this user's memory/YYYY-MM-DD.md.

    run_flush_llm(system_prompt: str, user_prompt: str) -> str should return the model's reply text.
    Only appends if reply is non-empty and not the silent token. Creates memory/ dir and file if needed.
    """
    if not is_flush_enabled():
        return
    try:
        root = get_memory_root(root_dir, user_id)
    except ValueError:
        return
    system_prompt = resolve_memory_flush_system_prompt()
    user_prompt = resolve_memory_flush_prompt(now_utc=now_utc)
    reply = run_flush_llm(system_prompt, user_prompt)
    if not reply or not reply.strip():
        return
    stripped = reply.strip()
    if stripped.lower().startswith(SILENT_REPLY_TOKEN.lower()):
        stripped = stripped[len(SILENT_REPLY_TOKEN) :].strip()
    if not stripped:
        return
    date_stamp = _format_date_stamp(now_utc)
    memory_dir = root / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    target = memory_dir / f"{date_stamp}.md"
    block = f"\n\n---\n\n{stripped}\n"
    try:
        target.write_text(target.read_text(encoding="utf-8", errors="replace") + block, encoding="utf-8")
    except FileNotFoundError:
        target.write_text(block.lstrip(), encoding="utf-8")
