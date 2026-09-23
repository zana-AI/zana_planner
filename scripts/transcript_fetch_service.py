#!/usr/bin/env python3
"""Residential worker for production video_transcript_fetch_jobs.

Run this on a home/residential machine, never on the Xaana VM. It uses the
existing SSH-to-Postgres bridge, claims one queued video, fetches subtitles
with the laptop-only fetchers, and writes successes to video_transcript.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from typing import Optional, Tuple

HOST = "root@169.58.186.195"
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{6,20}$")


def sql(statement: str) -> str:
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", HOST, "docker", "exec", "-i", "zana-postgres", "psql",
         "-v", "ON_ERROR_STOP=1", "-U", "zana", "-d", "zana", "-At", "-P", "footer=off"],
        input=statement, text=True, capture_output=True, encoding="utf-8", check=True,
    )
    return result.stdout.strip()


def claim(lease_seconds: int) -> Optional[Tuple[str, int]]:
    result = sql(
        "WITH candidate AS ("
        " SELECT video_id FROM video_transcript_fetch_jobs"
        " WHERE (status = 'queued' AND available_at <= now())"
        "    OR (status = 'processing' AND leased_until < now())"
        " ORDER BY priority DESC, requested_at ASC FOR UPDATE SKIP LOCKED LIMIT 1"
        ") UPDATE video_transcript_fetch_jobs job"
        " SET status = 'processing', attempt_count = job.attempt_count + 1,"
        f" leased_until = now() + interval '{max(60, lease_seconds)} seconds', last_error = NULL"
        " FROM candidate WHERE job.video_id = candidate.video_id"
        " RETURNING job.video_id, job.attempt_count;"
    )
    # psql prints the command tag ("UPDATE 0") for an UPDATE ... RETURNING
    # statement that claimed nothing, rather than an empty string.
    if not result or result.startswith("UPDATE "):
        return None
    video_id, attempts = result.split("|", 1)
    if not VIDEO_ID.fullmatch(video_id):
        raise RuntimeError(f"queue returned invalid video id: {video_id!r}")
    return video_id, int(attempts)


def finish(video_id: str, attempts: int, max_attempts: int, error: Optional[str] = None) -> None:
    if error is None:
        sql("UPDATE video_transcript_fetch_jobs SET status = 'completed', completed_at = now(), "
            f"leased_until = NULL, last_error = NULL WHERE video_id = '{video_id}';")
        return
    safe_error = " ".join(error.split())[:500].replace("'", "''")
    if attempts >= max_attempts:
        sql("UPDATE video_transcript_fetch_jobs SET status = 'failed', leased_until = NULL, "
            f"last_error = '{safe_error}' WHERE video_id = '{video_id}';")
        return
    delay = min(3600, 60 * (2 ** min(attempts - 1, 6)))
    sql("UPDATE video_transcript_fetch_jobs SET status = 'queued', leased_until = NULL, "
        f"available_at = now() + interval '{delay} seconds', last_error = '{safe_error}' "
        f"WHERE video_id = '{video_id}';")


def work_one(fetch_delay: float, lease_seconds: int, max_attempts: int) -> bool:
    job = claim(lease_seconds)
    if not job:
        return False
    video_id, attempts = job
    print(f"{video_id}: claimed ({attempts}/{max_attempts})", flush=True)
    try:
        from fetch_transcripts import fetch_with_backoff, push
        if not fetch_with_backoff(video_id, force=False, delay=fetch_delay) or not push(video_id):
            raise RuntimeError("caption fetch or cache upload failed")
    except Exception as exc:  # noqa: BLE001
        finish(video_id, attempts, max_attempts, str(exc))
        print(f"{video_id}: deferred: {exc}", file=sys.stderr, flush=True)
        return True
    finish(video_id, attempts, max_attempts)
    print(f"{video_id}: completed", flush=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--poll-seconds", type=float, default=20.0)
    parser.add_argument("--fetch-delay", type=float, default=30.0)
    parser.add_argument("--lease-seconds", type=int, default=900)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    while True:
        handled = work_one(args.fetch_delay, args.lease_seconds, max(1, args.max_attempts))
        if args.once:
            return 0
        if not handled:
            time.sleep(max(1, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
