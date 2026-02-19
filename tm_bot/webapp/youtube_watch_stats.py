"""
Append-only storage for YouTube watch stats (JSONL under ROOT_DIR).
No DB for now; file path: ROOT_DIR/youtube_watch_stats/youtube_watch_stats.jsonl

Also helpers for signed user token (fallback when init_data is empty, e.g. inline web_app).
"""

import os
import json
import hmac
import hashlib
import base64
from datetime import datetime
from typing import Any, List, Optional


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


def create_user_token(user_id: int, bot_token: str) -> str:
    """Create a signed token for user_id (use bot_token as secret). Safe to put in URL."""
    payload = str(user_id)
    sig = hmac.new(
        bot_token.encode() if isinstance(bot_token, str) else bot_token,
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:16]
    return base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode().rstrip("=")


def verify_user_token(token: str, bot_token: str) -> Optional[int]:
    """Verify token and return user_id or None."""
    if not token or not bot_token:
        return None
    try:
        padded = token + "=" * (4 - len(token) % 4)
        raw = base64.urlsafe_b64decode(padded)
        payload = raw.decode("utf-8")
        uid_str, sig = payload.split(":", 1)
        expected = hmac.new(
            bot_token.encode() if isinstance(bot_token, str) else bot_token,
            uid_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:16]
        if sig != expected:
            return None
        return int(uid_str)
    except Exception:
        return None


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
