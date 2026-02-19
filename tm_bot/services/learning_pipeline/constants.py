"""
Constants and helpers for the content-to-learning pipeline.
"""

from typing import Dict, List

PIPELINE_VERSION = "v1"

STAGE_ORDER: List[str] = [
    "queued",
    "resolve",
    "fetch",
    "transcribe",
    "segment",
    "embed",
    "summarize",
    "concept_extract",
    "quiz_generate",
    "done",
]

STAGE_PROGRESS: Dict[str, int] = {
    "queued": 0,
    "resolve": 10,
    "fetch": 20,
    "transcribe": 35,
    "segment": 50,
    "embed": 65,
    "summarize": 78,
    "concept_extract": 88,
    "quiz_generate": 96,
    "done": 100,
}

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = (30, 120, 600)

MAX_ARTICLE_CHARS = 200_000
MAX_AUDIO_DURATION_SECONDS = 4 * 60 * 60
DEFAULT_FETCH_TIMEOUT_SECONDS = 20
