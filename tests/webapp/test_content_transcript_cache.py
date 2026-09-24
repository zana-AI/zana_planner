"""Viewer reads cache and queues work without fetching inline."""
import pytest


def test_cache_hit_skips_queue(monkeypatch):
    from webapp.routers import content
    from repositories import video_transcript_repo, video_transcript_fetch_queue_repo
    cached = {"available": True, "cues": [{"start": 0, "end": 1, "text": "Cached"}]}
    monkeypatch.setattr(video_transcript_repo.VideoTranscriptRepository, "get", lambda *_: cached)
    monkeypatch.setattr(video_transcript_fetch_queue_repo.VideoTranscriptFetchQueueRepository, "enqueue",
                        lambda *_: pytest.fail("cached video must not queue"))
    assert content._transcript_for_video("dQw4w9WgXcQ") is cached


@pytest.mark.parametrize("state,error,status", [
    ("queued", None, "pending"), ("processing", None, "pending"),
    ("failed", "no_captions", "unavailable"), ("failed", "unavailable", "unavailable"),
    ("failed", "attempts_exhausted", "failed"), ("failed", "private worker details", "failed"),
])
def test_cache_miss_queues_without_live_fetch(monkeypatch, state, error, status):
    from webapp.routers import content
    from repositories import video_transcript_repo, video_transcript_fetch_queue_repo
    import utils.youtube_utils as youtube
    queued = []
    monkeypatch.setattr(video_transcript_repo.VideoTranscriptRepository, "get", lambda *_: None)
    monkeypatch.setattr(video_transcript_fetch_queue_repo.VideoTranscriptFetchQueueRepository, "enqueue",
                        lambda _, v: queued.append(v))
    monkeypatch.setattr(video_transcript_fetch_queue_repo.VideoTranscriptFetchQueueRepository, "fetch_state",
                        lambda *_: {"status": state, "last_error": error})
    monkeypatch.setattr(youtube, "get_video_transcript", lambda *_a, **_k: pytest.fail("HTTP must not fetch"))
    assert content._transcript_for_video("dQw4w9WgXcQ") == {
        "available": False, "cues": [], "pending": status == "pending", "status": status}
    assert queued == ["dQw4w9WgXcQ"]


def test_queue_failure_does_not_claim_video_has_no_captions(monkeypatch):
    from webapp.routers import content
    from repositories import video_transcript_repo, video_transcript_fetch_queue_repo
    monkeypatch.setattr(video_transcript_repo.VideoTranscriptRepository, "get", lambda *_: None)
    def fail(*_):
        raise RuntimeError("Queue offline")
    monkeypatch.setattr(video_transcript_fetch_queue_repo.VideoTranscriptFetchQueueRepository, "enqueue", fail)
    assert content._transcript_for_video("dQw4w9WgXcQ")["status"] == "failed"


def test_worker_finishing_during_request_returns_new_captions(monkeypatch):
    from webapp.routers import content
    from repositories import video_transcript_repo, video_transcript_fetch_queue_repo
    cached = {"available": True, "cues": [{"start": 0, "end": 1, "text": "Ready"}]}
    reads = iter([None, cached])
    monkeypatch.setattr(video_transcript_repo.VideoTranscriptRepository, "get", lambda *_: next(reads))
    monkeypatch.setattr(video_transcript_fetch_queue_repo.VideoTranscriptFetchQueueRepository, "enqueue", lambda *_: None)
    monkeypatch.setattr(video_transcript_fetch_queue_repo.VideoTranscriptFetchQueueRepository, "fetch_state",
                        lambda *_: {"status": "completed", "last_error": None})
    assert content._transcript_for_video("dQw4w9WgXcQ") is cached


def test_saving_youtube_content_requests_transcript(monkeypatch):
    from repositories.content_repo import ContentRepository
    from repositories.video_transcript_fetch_queue_repo import VideoTranscriptFetchQueueRepository
    queued = []
    repo = ContentRepository()
    monkeypatch.setattr(repo, "get_content_by_id", lambda _: {
        "provider": "youtube", "metadata_json": {"video_id": "dQw4w9WgXcQ"}})
    monkeypatch.setattr(VideoTranscriptFetchQueueRepository, "enqueue", lambda _, v: queued.append(v))
    repo.request_youtube_transcript("content-id")
    assert queued == ["dQw4w9WgXcQ"]
