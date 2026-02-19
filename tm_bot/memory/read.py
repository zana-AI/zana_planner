"""
Read snippets from per-user MEMORY.md or memory/*.md. No vector DB required.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union

from memory.config import get_memory_root


def memory_get(
    path: str,
    root_dir: Union[str, Path],
    user_id: str,
    from_line: Optional[int] = None,
    lines: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Read from this user's memory root: MEMORY.md or memory/<path>.
    Optional from_line (1-based) and lines to return a slice.
    """
    if not path or not path.strip():
        return {"path": path or "", "text": "", "error": "path is required"}
    path_str = path.strip().replace("\\", "/")
    if ".." in path_str or path_str.startswith("/"):
        return {"path": path_str, "text": "", "error": "Invalid path (no traversal or absolute)"}
    try:
        root = get_memory_root(root_dir, user_id)
    except ValueError as e:
        return {"path": path_str, "text": "", "error": str(e)}
    if path_str.lower() == "memory.md":
        full_path = root / "MEMORY.md"
    elif path_str.lower().startswith("memory/"):
        full_path = root / path_str
    else:
        full_path = root / path_str
    try:
        if not full_path.is_file():
            return {"path": path_str, "text": "", "error": "File not found"}
        try:
            full_path.resolve().relative_to(root.resolve())
        except ValueError:
            return {"path": path_str, "text": "", "error": "Path outside memory root"}
    except OSError:
        return {"path": path_str, "text": "", "error": "File not found"}
    try:
        text = full_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {"path": path_str, "text": "", "error": str(e)}
    if from_line is not None or lines is not None:
        line_list = text.splitlines()
        start = (from_line or 1) - 1
        if start < 0:
            start = 0
        end = start + (lines or len(line_list)) if lines else len(line_list)
        line_list = line_list[start:end]
        text = "\n".join(line_list)
    return {"path": path_str, "text": text}
