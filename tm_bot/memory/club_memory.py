"""
Club memory — file-based, mirrors the per-user memory structure.

Filesystem layout (relative to root_dir):
  clubs/<club_id>/MEMORY.md              — structured facts / key-value index
  clubs/<club_id>/memory/YYYY-MM-DD.md   — free-text timestamped notes

Qdrant: same collection as user memory. Club UUIDs never collide with Telegram
integer user IDs, so no partition is needed — the user_id filter value is just
the club_id string.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

from memory.config import get_memory_root
from memory.read import memory_get
from memory.search import memory_search
from memory.write import memory_write


def _clubs_root(root_dir: Union[str, Path]) -> Path:
    return Path(root_dir).resolve() / "clubs"


def club_memory_write(
    text: str,
    root_dir: Union[str, Path],
    club_id: str,
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Append a free-text note to this club's memory/YYYY-MM-DD.md."""
    return memory_write(text, _clubs_root(root_dir), club_id, now_utc=now_utc)


def club_memory_get(
    path: str,
    root_dir: Union[str, Path],
    club_id: str,
    **kwargs,
) -> Dict[str, Any]:
    """Read a file from this club's memory root."""
    return memory_get(path, _clubs_root(root_dir), club_id, **kwargs)


def club_memory_search(
    query: str,
    root_dir: Union[str, Path],
    club_id: str,
    **kwargs,
) -> Dict[str, Any]:
    """Semantic (Qdrant-first) search over this club's memory files."""
    return memory_search(query, str(_clubs_root(root_dir)), club_id, **kwargs)


def club_memory_upsert_fact(
    root_dir: Union[str, Path],
    club_id: str,
    field_key: str,
    value: str,
) -> None:
    """
    Upsert a key: value line in the club's MEMORY.md.
    Creates the file if it doesn't exist. Updates the line in place if the key exists.
    """
    try:
        club_root = get_memory_root(_clubs_root(root_dir), club_id)
        club_root.mkdir(parents=True, exist_ok=True)
        memory_md = club_root / "MEMORY.md"

        content = memory_md.read_text(encoding="utf-8", errors="replace") if memory_md.is_file() else ""
        lines = content.splitlines()
        key_prefix = f"{field_key}:"
        updated = False
        new_lines = []
        for line in lines:
            if line.startswith(key_prefix):
                new_lines.append(f"{field_key}: {value}")
                updated = True
            else:
                new_lines.append(line)
        if not updated:
            new_lines.append(f"{field_key}: {value}")

        memory_md.write_text("\n".join(new_lines).strip() + "\n", encoding="utf-8")
    except Exception:
        pass


def club_memory_format_for_prompt(
    root_dir: Union[str, Path],
    club_id: str,
) -> str:
    """
    Return the club's MEMORY.md content formatted for LLM prompt injection.
    Returns empty string if the file doesn't exist or is empty.
    """
    try:
        club_root = get_memory_root(_clubs_root(root_dir), club_id)
        memory_md = club_root / "MEMORY.md"
        if not memory_md.is_file():
            return ""
        text = memory_md.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            return ""
        return f"Club memory (facts the bot has learned about this club):\n{text}"
    except Exception:
        return ""
