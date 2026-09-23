"""The watch-page fallback must become a durable subtitle cache entry."""

import pytest


def test_live_transcript_is_saved_after_cache_miss(monkeypatch):
    pytest.importorskip("fastapi")
    from webapp.routers import content as content_router
    import repositories.video_transcript_repo as transcript_repo_module
    import utils.youtube_utils as youtube_utils

    instances = []

    class FakeTranscriptRepository:
        def __init__(self):
            self.upsert_calls = []
            instances.append(self)

        def get(self, _video_id):
            return None

        def upsert(self, **kwargs):
            self.upsert_calls.append(kwargs)
            return len(kwargs["cues"])

    live = {
        "available": True,
        "language": "fr",
        "source": "automatic",
        "cues": [{"start": 0.0, "end": 2.5, "text": "Bonjour"}],
    }
    monkeypatch.setattr(transcript_repo_module, "VideoTranscriptRepository", FakeTranscriptRepository)
    monkeypatch.setattr(youtube_utils, "get_video_transcript", lambda *_args, **_kwargs: live)

    assert content_router._transcript_for_video("dQw4w9WgXcQ") is live
    assert instances[-1].upsert_calls == [{
        "video_id": "dQw4w9WgXcQ",
        "cues": live["cues"],
        "language": "fr",
        "is_generated": True,
    }]


def test_cached_transcript_skips_live_fetch(monkeypatch):
    pytest.importorskip("fastapi")
    from webapp.routers import content as content_router
    import repositories.video_transcript_repo as transcript_repo_module
    import utils.youtube_utils as youtube_utils

    cached = {"available": True, "cues": [{"start": 0, "end": 1, "text": "Cached"}]}

    class FakeTranscriptRepository:
        def get(self, _video_id):
            return cached

    monkeypatch.setattr(transcript_repo_module, "VideoTranscriptRepository", FakeTranscriptRepository)
    monkeypatch.setattr(youtube_utils, "get_video_transcript", lambda *_args, **_kwargs: pytest.fail("live fetch"))

    assert content_router._transcript_for_video("dQw4w9WgXcQ") is cached


def test_failed_live_transcript_is_queued_for_residential_worker(monkeypatch):
    pytest.importorskip("fastapi")
    from webapp.routers import content as content_router
    import repositories.video_transcript_repo as transcript_repo_module
    import repositories.video_transcript_fetch_queue_repo as queue_repo_module
    import utils.youtube_utils as youtube_utils

    queued = []

    class FakeTranscriptRepository:
        def get(self, _video_id):
            return None

    class FakeQueueRepository:
        def enqueue(self, video_id):
            queued.append(video_id)

    unavailable = {"available": False, "cues": []}
    monkeypatch.setattr(transcript_repo_module, "VideoTranscriptRepository", FakeTranscriptRepository)
    monkeypatch.setattr(queue_repo_module, "VideoTranscriptFetchQueueRepository", FakeQueueRepository)
    monkeypatch.setattr(youtube_utils, "get_video_transcript", lambda *_args, **_kwargs: unavailable)

    assert content_router._transcript_for_video("dQw4w9WgXcQ") is unavailable
    assert queued == ["dQw4w9WgXcQ"]


def test_saving_youtube_content_requests_transcript_queue(monkeypatch):
    from repositories.content_repo import ContentRepository
    import repositories.video_transcript_fetch_queue_repo as queue_repo_module

    queued = []

    class FakeQueueRepository:
        def enqueue(self, video_id):
            queued.append(video_id)

    repo = ContentRepository()
    monkeypatch.setattr(
        repo,
        "get_content_by_id",
        lambda _content_id: {
            "provider": "youtube",
            "metadata_json": {"video_id": "dQw4w9WgXcQ"},
        },
    )
    monkeypatch.setattr(queue_repo_module, "VideoTranscriptFetchQueueRepository", FakeQueueRepository)

    repo.request_youtube_transcript("content-id")

    assert queued == ["dQw4w9WgXcQ"]


def test_queue_does_not_requeue_cached_transcript(monkeypatch):
    import repositories.video_transcript_fetch_queue_repo as queue_repo_module

    class FakeTranscriptRepository:
        def get(self, _video_id):
            return {"cues": [{"start": 0, "end": 1, "text": "Cached"}]}

    def unexpected_session():
        pytest.fail("Cached transcript must not create a queue job")

    monkeypatch.setattr(queue_repo_module, "get_db_session", unexpected_session)
    import repositories.video_transcript_repo as transcript_repo_module
    monkeypatch.setattr(transcript_repo_module, "VideoTranscriptRepository", FakeTranscriptRepository)

    queue_repo_module.VideoTranscriptFetchQueueRepository().enqueue("dQw4w9WgXcQ")
