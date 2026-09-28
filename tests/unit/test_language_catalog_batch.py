"""Content-import guards: exact scope, truthful metadata and safe merging."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = load_script("build_language_catalog")
publish = load_script("publish_language_catalog")


@pytest.fixture
def batch():
    return {"status": "metadata_verified", "batch_id": "test", "items": [
        {"video_id": f"test{i:07d}", "url": f"https://www.youtube.com/watch?v=test{i:07d}",
         "language": "fr" if i < 100 else "en", "title": "A day out", "creator": "Creator",
         "duration_seconds": 600, "availability": "public", "embedding_status": "allowed",
         "age_limit": 0, "caption_status": "source_track_advertised_not_cached",
         "caption_language": "fr" if i < 100 else "en", "caption_is_generated": False,
         "target_level": "A2-B1", "selection_reason": "Everyday life.",
         "channel_id": "channel", "verified_at": "2026-09-27T10:00:00+00:00"}
        for i in range(200)]}


@pytest.mark.parametrize("duration,expected", [(479, False), (480, True), (1440, True), (1441, False), (None, False)])
def test_duration_boundaries(duration, expected):
    assert build.eligible({"id": "abcdefghijk", "title": "A day out", "duration": duration}, {}) is expected


@pytest.mark.parametrize("field,value", [
    ("duration_seconds", 60), ("duration_seconds", float("nan")),
    ("url", "https://other.example/watch"), ("caption_language", "en"),
    ("embedding_status", "unchecked"), ("availability", "private"),
    ("age_limit", 18), ("verified_at", None),
])
def test_publishing_rejects_invalid_or_unverified_entries(batch, field, value):
    batch["items"][0][field] = value
    with pytest.raises(ValueError):
        publish.validate_batch(batch)


def test_publishing_rejects_duplicates_and_wrong_language_balance(batch):
    batch["items"][1] = deepcopy(batch["items"][0])
    with pytest.raises(ValueError, match="unique"):
        publish.validate_batch(batch)
    batch["items"][1]["video_id"] = "abcdefghijk"
    batch["items"][1]["language"] = "en"
    with pytest.raises(ValueError, match="exactly"):
        publish.validate_batch(batch)


def test_merge_preserves_unrelated_content_and_is_idempotent(batch):
    catalog = {"version": 1, "categories": [
        {"id": "french", "language": "fr", "title": "French", "topics": [
            {"id": "watch", "title": "Watch", "items": [{"id": "old-fr", "title": "Old French", "order": 1}]},
        ]},
        {"id": "english", "language": "en", "title": "English", "topics": [
            {"id": "watch", "title": "Watch", "items": [{"id": "old-en", "title": "Old English", "order": 1}]},
        ]},
        {"id": "body", "language": None, "title": "Body", "topics": []},
    ]}
    publish.validate_batch(batch)
    original = deepcopy(catalog)
    merged = publish.merge_catalog(catalog, batch)
    released = [i for c in merged["categories"] for t in c["topics"] for i in t.get("items", [])
                if i["id"].startswith("language-200-")]
    assert {i["id"] for i in released} == {"language-200-" + i["video_id"] for i in batch["items"]}
    assert all("subtitles_available" not in i and not i.get("starter") for i in released)
    assert catalog == original
    assert merged["categories"][2] == original["categories"][2]
    assert merged["categories"][0]["topics"][0]["items"][0] == original["categories"][0]["topics"][0]["items"][0]
    assert publish.merge_catalog(merged, batch) == merged


def test_selection_replaces_rejected_candidates_and_refuses_shortfall():
    sources = [{"id": language, "language": language, "url": "https://www.youtube.com/@example/videos",
                "target_level": "A2-B1", "reason": "Everyday life", "max_items": 2} for language in ("fr", "en")]
    collected = {language: {"channel": "Creator", "channel_id": "channel", "retrieved_at": "today",
                           "entries": [{"id": f"{language}{i:09d}", "duration": 600, "title": "A day out"}
                                       for i in range(3)]} for language in ("fr", "en")}
    picked = build.select(sources, collected, set(), per_language=2,
                          verify=lambda e, s, c: None if e["id"].endswith("0") else {})
    assert len(picked) == 4
    assert all(not i["video_id"].endswith("0") for i in picked)
    with pytest.raises(ValueError, match="Insufficient"):
        build.select(sources, collected, set(), per_language=3)


def test_review_escapes_source_titles(batch, tmp_path):
    batch["items"][0]["title"] = '<script>alert("x")</script>'
    target = tmp_path / "review.html"
    publish.write_review(batch, target)
    html = target.read_text(encoding="utf-8")
    assert '<script>alert("x")</script>' not in html
    assert "&lt;script&gt;" in html


@pytest.mark.parametrize("private_conflict,public_count", [(True, 200), (False, 199)])
def test_publication_rejects_private_conflicts_and_missing_public_rows(batch, private_conflict, public_count):
    statements = []

    class Result:
        def mappings(self):
            return self

        def all(self):
            return [{"canonical_url": batch["items"][0]["url"], "visibility": "private"}] if private_conflict else []

        def scalar_one(self):
            return public_count

    class Session:
        def execute(self, statement, params=None):
            statements.append(str(statement))
            return Result()

    # Normally supplied by the verified manifest; needed by the INSERT path.
    for item in batch["items"]:
        item["level_evidence"] = "Source/title estimate"
    with pytest.raises(ValueError):
        publish.insert_public_content(batch, Session())
    assert not any("UPDATE content" in sql or "DELETE" in sql for sql in statements)
    if private_conflict:
        assert not any("INSERT INTO content" in sql for sql in statements)
