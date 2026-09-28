"""The explicit share action exposes only the validated destinations."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from repositories.explore_repo import ExploreRepository
from services.explore_config import ExploreCatalog, explore_config_loader
from webapp.routers import content


def test_share_route_validates_level_and_invalidates_explore_cache(monkeypatch):
    calls = []

    def share(_self, content_id, user_id, destination, language, level):
        calls.append((content_id, user_id, destination, language, level))
        return {"path": "/youtube-watch?video_id=abcdefghijk", "already_in_explore": False}

    monkeypatch.setattr(ExploreRepository, "share_library_content", share)
    monkeypatch.setattr(explore_config_loader, "invalidate", lambda: calls.append("invalidated"))
    app = FastAPI()
    app.include_router(content.router)
    app.dependency_overrides[content.get_current_user] = lambda: 7
    with TestClient(app) as client:
        invalid = client.post("/api/content/item/share", json={"destination": "explore", "level": "Z9"})
        assert invalid.status_code == 422
        response = client.post("/api/content/item/share", json={"destination": "explore", "language": "fr", "level": "B2"})
    assert response.status_code == 200
    assert response.json()["already_in_explore"] is False
    assert calls == [("item", "7", "explore", "fr", "B2"), "invalidated"]


def test_save_repairs_only_a_published_explore_video(monkeypatch):
    class Repo:
        public = False
        repaired = False

        def get_content_by_id(self, _id):
            return {"provider": "youtube", "metadata_json": {"video_id": "abcdefghijk"}}

        def can_access_content(self, _user, _id):
            return self.public

        def make_curated_video_public(self, _id):
            self.public = True
            self.repaired = True

        def claim_content_owner(self, _id, _user):
            pass

        def add_user_content(self, _user, _id):
            return "saved-row"

    repo = Repo()
    catalog = ExploreCatalog.model_validate({"categories": [{"id": "french", "title": "French", "topics": [
        {"id": "watch", "title": "Watch", "items": [{"id": "video", "title": "Video",
          "native_ref": "/youtube-watch?video_id=abcdefghijk"}]}
    ]}]})
    monkeypatch.setattr(content, "get_content_repo", lambda: repo)
    monkeypatch.setattr(content, "is_admin", lambda _user: False)
    monkeypatch.setattr(explore_config_loader, "load", lambda: catalog)
    app = FastAPI()
    app.include_router(content.router)
    app.dependency_overrides[content.get_current_user] = lambda: 7
    with TestClient(app) as client:
        response = client.post("/api/user-content", json={"content_id": "item"})
    assert response.status_code == 200
    assert repo.repaired and response.json()["user_content_id"] == "saved-row"


def test_library_response_separates_estimated_level_from_subtitle(monkeypatch):
    class Repo:
        def get_user_contents(self, *_args, **_kwargs):
            return [{"id": "pdf", "provider": "telegram_pdf", "title": "Reader",
                     "description": "A2-B1 estimate. Everyday reading.", "metadata_json": {}, "buckets": []}]

        def get_user_content_facets(self, *_args, **_kwargs):
            return {}

    monkeypatch.setattr(content, "get_content_repo", lambda: Repo())
    app = FastAPI()
    app.include_router(content.router)
    app.dependency_overrides[content.get_current_user] = lambda: 7
    with TestClient(app) as client:
        response = client.get("/api/my-contents")
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["description"] == "Everyday reading."
    assert item["metadata_json"]["level"] == "~A2–B1"
