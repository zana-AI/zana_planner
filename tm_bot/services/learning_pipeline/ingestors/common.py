"""
Common helpers for ingestors.
"""

from __future__ import annotations

import json
import re
from typing import List
from urllib.parse import urljoin

import requests

from services.learning_pipeline.constants import DEFAULT_FETCH_TIMEOUT_SECONDS
from services.learning_pipeline.security import validate_safe_http_url
from services.learning_pipeline.types import SegmentRecord


def fetch_text_url(url: str, timeout_seconds: int = DEFAULT_FETCH_TIMEOUT_SECONDS) -> str:
    response = safe_get(url, timeout_seconds=timeout_seconds)
    response.raise_for_status()
    return response.text


def safe_get(
    url: str,
    timeout_seconds: int = DEFAULT_FETCH_TIMEOUT_SECONDS,
    headers: dict | None = None,
    stream: bool = False,
    max_redirects: int = 5,
):
    request_headers = {"User-Agent": "XaanaLearningBot/1.0"}
    if headers:
        request_headers.update(headers)
    current_url = url
    for _ in range(max_redirects + 1):
        validate_safe_http_url(current_url)
        response = requests.get(
            current_url,
            timeout=timeout_seconds,
            headers=request_headers,
            stream=stream,
            allow_redirects=False,
        )
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location")
            if not location:
                return response
            current_url = urljoin(current_url, location)
            continue
        return response
    raise ValueError("Too many redirects while fetching URL")


def parse_vtt_to_segments(vtt_text: str) -> List[SegmentRecord]:
    lines = (vtt_text or "").splitlines()
    segments: List[SegmentRecord] = []
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        if "-->" not in line:
            idx += 1
            continue
        start_ms, end_ms = _parse_vtt_timestamp_pair(line)
        idx += 1
        text_lines = []
        while idx < len(lines) and lines[idx].strip():
            piece = re.sub(r"<[^>]+>", "", lines[idx]).strip()
            if piece:
                text_lines.append(piece)
            idx += 1
        text_value = " ".join(text_lines).strip()
        if text_value:
            segments.append(
                SegmentRecord(
                    text=text_value,
                    start_ms=start_ms,
                    end_ms=end_ms,
                )
            )
        idx += 1
    return segments


def parse_json3_to_segments(json3_text: str) -> List[SegmentRecord]:
    try:
        data = json.loads(json3_text or "{}")
    except Exception:
        return []
    events = data.get("events") or []
    segments: List[SegmentRecord] = []
    for event in events:
        segs = event.get("segs") or []
        text_parts = []
        for seg in segs:
            value = (seg.get("utf8") or "").strip()
            if value:
                text_parts.append(value)
        text_value = " ".join(text_parts).strip()
        if not text_value:
            continue
        start_ms = event.get("tStartMs")
        duration_ms = event.get("dDurationMs")
        end_ms = None
        if isinstance(start_ms, (int, float)) and isinstance(duration_ms, (int, float)):
            end_ms = int(start_ms + duration_ms)
            start_ms = int(start_ms)
        else:
            start_ms = None
        segments.append(
            SegmentRecord(
                text=text_value,
                start_ms=start_ms,
                end_ms=end_ms,
            )
        )
    return segments


def _parse_vtt_timestamp_pair(line: str) -> tuple[int | None, int | None]:
    parts = [part.strip() for part in line.split("-->")]
    if len(parts) != 2:
        return None, None
    return _parse_vtt_timestamp(parts[0]), _parse_vtt_timestamp(parts[1])


def _parse_vtt_timestamp(value: str) -> int | None:
    match = re.match(r"(?:(\d+):)?(\d+):(\d+)\.(\d+)", value.strip())
    if not match:
        return None
    h = int(match.group(1) or 0)
    m = int(match.group(2) or 0)
    s = int(match.group(3) or 0)
    ms = int(match.group(4) or 0)
    total_ms = (h * 3600 + m * 60 + s) * 1000 + ms
    return total_ms
