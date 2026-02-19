"""
Append-only storage for YouTube watch stats (JSONL under ROOT_DIR).
No DB for now; file path: ROOT_DIR/youtube_watch_stats/youtube_watch_stats.jsonl
"""

import os
import json
from datetime import datetime
from typing import Any, List


def _stats_dir(root_dir: str) -> str:
    d = os.path.join(root_dir, "youtube_watch_stats")
    os.makedirs(d, exist_ok=True)
    return d


def _stats_path(root_dir: str) -> str:
    return os.path.join(_stats_dir(root_dir), "youtube_watch_stats.jsonl")


def append_stats(
    root_dir: str,
    user_id: int,
    video_id: str,
    time_spent_seconds: float,
    segments: List[List[float]],
    closed_via: str = "done",
) -> None:
    """Append one stats record to the JSONL file."""
    record = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "user_id": user_id,
        "video_id": video_id,
        "time_spent_seconds": round(time_spent_seconds, 1),
        "segments": segments,
        "closed_via": closed_via,
    }
    path = _stats_path(root_dir)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def format_summary_message(
    video_id: str,
    time_spent_seconds: float,
    segments: List[List[float]],
) -> str:
    """Human-readable summary for the Telegram message."""
    mins = int(time_spent_seconds // 60)
    secs = int(time_spent_seconds % 60)
    time_str = f"{mins} min {secs} s" if mins else f"{secs} s"
    lines = [
        "📺 YouTube watch summary",
        f"Video: {video_id}",
        f"Time on page: {time_str}",
    ]
    if segments:
        seg_strs = [f"{int(s[0])}s–{int(s[1])}s" for s in segments[:10]]
        if len(segments) > 10:
            seg_strs.append(f"... +{len(segments) - 10} more")
        lines.append("Segments watched: " + ", ".join(seg_strs))
    return "\n".join(lines)
