"""One durable, timed cloud attempt, followed by the residential queue."""
import asyncio
import json
import logging
import os
from pathlib import Path
import subprocess
import sys

from repositories.video_transcript_fetch_queue_repo import VideoTranscriptFetchQueueRepository, LeaseLost
from services.caption_models import Transcript

logger = logging.getLogger(__name__)
FETCHER = Path(__file__).resolve().parents[2] / "scripts" / "caption_relay" / "fetch.py"


def work_one():
    repo = VideoTranscriptFetchQueueRepository()
    job = repo.claim()
    if not job:
        return
    video_id = job["video_id"]
    transcript, error = None, "fetch_failed"
    try:
        result = subprocess.run([sys.executable, str(FETCHER), video_id], capture_output=True,
                                text=True, encoding="utf-8", timeout=45, check=True,
                                env={k: v for k, v in os.environ.items() if k in (
                                    "PATH", "SYSTEMROOT", "WINDIR", "LANG", "HOME", "PYTHONPATH")})
        payload = json.loads(result.stdout)
        if payload.get("transcript"):
            transcript = Transcript.model_validate(payload["transcript"]).model_dump()
        else:
            error = payload.get("error", "fetch_failed")
    except subprocess.TimeoutExpired:
        error = "timeout"
    except Exception:
        error = "fetch_failed"
    try:
        repo.finish(video_id, job["lease_token"], transcript=transcript, error=error)
        logger.info("Caption server %s: %s", video_id, "cached" if transcript else "queued for relay")
    except LeaseLost:
        logger.info("Caption server %s: lease superseded", video_id)


async def run():
    while True:
        try:
            await asyncio.to_thread(work_one)
        except Exception:
            logger.exception("Caption dispatcher iteration failed")
        await asyncio.sleep(10)
