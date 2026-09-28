"""Guards for editing database-backed Explore content."""
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("manage_explore_catalog", ROOT / "scripts/manage_explore_catalog.py")
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)


def test_digest_ignores_mapping_order_but_detects_content_changes():
    assert manage.digest({"version": 1, "categories": []}) == manage.digest({"categories": [], "version": 1})
    assert manage.digest({"categories": [], "version": 1}) != manage.digest({"categories": [1], "version": 1})


def test_import_rejects_empty_or_duplicate_catalog():
    with pytest.raises(ValueError, match="at least one category"):
        manage.validate_document({"version": 1, "categories": []})
    with pytest.raises(ValueError, match="Duplicate Explore category ID"):
        manage.validate_document({"version": 1, "categories": [
            {"id": "french", "title": "French"}, {"id": "french", "title": "French again"},
        ]})


def test_new_video_requires_public_content_row():
    previous = {"categories": [{"topics": [{"items": []}]}]}
    updated = {"categories": [{"topics": [{"items": [
        {"id": "new", "type": "video", "native_ref": "/youtube-watch?video_id=abcdefghijk"},
    ]}]}]}

    class Result:
        def __init__(self, urls):
            self.urls = urls

        def scalars(self):
            return self

        def all(self):
            return self.urls

    class Session:
        def __init__(self, urls):
            self.urls = urls

        def execute(self, statement, params):
            return Result(self.urls)

    with pytest.raises(ValueError, match="public content rows"):
        manage.require_new_videos_public(Session([]), previous, updated)
    manage.require_new_videos_public(
        Session(["https://www.youtube.com/watch?v=abcdefghijk"]), previous, updated
    )
