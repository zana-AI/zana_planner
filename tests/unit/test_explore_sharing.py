"""Explicit Library sharing must preserve access and avoid duplicate Explore cards."""
import json
from contextlib import nullcontext

import pytest

from repositories import explore_repo
from services.explore_config import catalog_video_ids, catalog_video_levels, separate_level, ExploreCatalog


class _Result:
    def __init__(self, value):
        self.value = value

    def mappings(self):
        return self

    def one_or_none(self):
        return self.value

    def scalar(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value


class _Session:
    def __init__(self, content, document, saved=True):
        self.content = content
        self.document = document
        self.saved = saved
        self.catalog_writes = 0

    def execute(self, statement, params=None):
        sql = str(statement)
        if sql.startswith("SELECT * FROM content"):
            return _Result(self.content)
        if sql.startswith("SELECT EXISTS(SELECT 1 FROM user_content"):
            return _Result(self.saved)
        if sql.startswith("SELECT document FROM explore_catalog"):
            return _Result(self.document)
        if sql.startswith("UPDATE content SET visibility"):
            self.content["visibility"] = "public"
        elif sql.startswith("UPDATE content SET language"):
            self.content["language"] = params["language"]
            self.content["metadata_json"] = json.loads(params["metadata"])
        elif sql.startswith("UPDATE explore_catalog"):
            self.document = json.loads(params["document"])
            self.catalog_writes += 1
        else:
            raise AssertionError(sql)
        return _Result(None)


def _content(*, pdf=False):
    return {"id": "11111111-1111-1111-1111-111111111111",
            "provider": "telegram_pdf" if pdf else "youtube",
            "canonical_url": "" if pdf else "https://www.youtube.com/watch?v=abcdefghijk",
            "original_url": "", "metadata_json": {"mime_type": "application/pdf"} if pdf else {"video_id": "abcdefghijk"},
            "title": "Practice", "description": "Learn together", "author_channel": "Teacher",
            "owner_user_id": "7", "visibility": "private", "language": "fr", "thumbnail_url": None}


def _catalog():
    return {"version": 1, "categories": [{"id": "french", "title": "French", "language": "fr",
            "topics": [{"id": "watch", "title": "Watch", "items": []}]}]}


def test_sharing_pdf_link_requires_owner_and_does_not_list_in_explore(monkeypatch):
    session = _Session(_content(pdf=True), _catalog())
    monkeypatch.setattr(explore_repo, "get_db_session", lambda: nullcontext(session))
    with pytest.raises(PermissionError, match="PDF owner"):
        explore_repo.ExploreRepository().share_library_content(session.content["id"], "8", "link")
    assert session.content["visibility"] == "private"
    result = explore_repo.ExploreRepository().share_library_content(session.content["id"], "7", "link")
    assert result["path"] == "/pdf-reader?content_id=" + session.content["id"]
    assert session.content["visibility"] == "public"
    assert session.catalog_writes == 0


def test_sharing_video_link_makes_it_savable_without_listing_it(monkeypatch):
    session = _Session(_content(), _catalog())
    monkeypatch.setattr(explore_repo, "get_db_session", lambda: nullcontext(session))
    result = explore_repo.ExploreRepository().share_library_content(session.content["id"], "8", "link")
    assert result["path"] == "/youtube-watch?video_id=abcdefghijk"
    assert session.content["visibility"] == "public"
    assert session.catalog_writes == 0


def test_explore_share_is_public_and_idempotent_by_video_id(monkeypatch):
    session = _Session(_content(), _catalog())
    monkeypatch.setattr(explore_repo, "get_db_session", lambda: nullcontext(session))
    repo = explore_repo.ExploreRepository()
    first = repo.share_library_content(session.content["id"], "8", "explore", "fr", "B2")
    second = repo.share_library_content(session.content["id"], "8", "explore", "fr", "B2")
    assert first["already_in_explore"] is False
    assert second["already_in_explore"] is True
    assert session.content["visibility"] == "public"
    assert session.content["metadata_json"]["level"] == "B2"
    assert session.catalog_writes == 1
    items = session.document["categories"][0]["topics"][0]["items"]
    assert len(items) == 1 and items[0]["level"] == "B2"


def test_pdf_explore_share_creates_one_read_card(monkeypatch):
    session = _Session(_content(pdf=True), _catalog())
    monkeypatch.setattr(explore_repo, "get_db_session", lambda: nullcontext(session))
    repo = explore_repo.ExploreRepository()
    first = repo.share_library_content(session.content["id"], "7", "explore", "fr", "A2")
    second = repo.share_library_content(session.content["id"], "7", "explore", "fr", "A2")
    assert first["already_in_explore"] is False and second["already_in_explore"] is True
    read_topic = next(t for t in session.document["categories"][0]["topics"] if t["id"] == "read")
    assert len(read_topic["items"]) == 1
    assert read_topic["items"][0]["type"] == "pdf"
    assert read_topic["items"][0]["content_id"] == session.content["id"]


def test_duplicate_curated_video_does_not_add_another_card(monkeypatch):
    catalog = _catalog()
    catalog["categories"][0]["topics"][0]["items"].append({
        "id": "curated", "title": "Already here", "native_ref": "/youtube-watch?video_id=abcdefghijk"})
    session = _Session(_content(), catalog)
    monkeypatch.setattr(explore_repo, "get_db_session", lambda: nullcontext(session))
    result = explore_repo.ExploreRepository().share_library_content(session.content["id"], "8", "explore", "fr", "A2")
    assert result["already_in_explore"] is True
    assert session.catalog_writes == 0
    assert session.content["visibility"] == "public"


def test_hidden_curated_video_cannot_be_republished_by_sharing(monkeypatch):
    catalog = _catalog()
    catalog["categories"][0]["topics"][0]["items"].append({
        "id": "hidden", "title": "Hidden", "published": False,
        "native_ref": "/youtube-watch?video_id=abcdefghijk"})
    session = _Session(_content(), catalog)
    monkeypatch.setattr(explore_repo, "get_db_session", lambda: nullcontext(session))
    with pytest.raises(PermissionError, match="hidden"):
        explore_repo.ExploreRepository().share_library_content(session.content["id"], "8", "explore")
    assert session.catalog_writes == 0
    assert session.content["visibility"] == "private"


def test_legacy_level_moves_out_of_explore_subtitle():
    level, description = separate_level("A2-B1 estimate. Everyday stories for learners.")
    assert (level, description) == ("~A2–B1", "Everyday stories for learners.")
    catalog = ExploreCatalog.model_validate({"categories": [{"id": "french", "title": "French", "topics": [
        {"id": "watch", "title": "Watch", "items": [{"id": "one", "title": "Story",
          "native_ref": "/youtube-watch?video_id=abcdefghijk", "description": "B1 (stretch) estimate. Listen closely."}]}
    ]}]})
    assert catalog_video_levels(catalog) == {"abcdefghijk": "~B1+"}


def test_only_published_video_ids_can_repair_legacy_access():
    catalog = ExploreCatalog.model_validate({"categories": [{"id": "french", "title": "French", "topics": [
        {"id": "watch", "title": "Watch", "items": [
            {"id": "visible", "title": "Visible", "native_ref": "/youtube-watch?video_id=abcdefghijk"},
            {"id": "hidden", "title": "Hidden", "published": False,
             "native_ref": "/youtube-watch?video_id=12345678901"},
        ]}
    ]}]})
    assert catalog_video_ids(catalog) == {"abcdefghijk"}
