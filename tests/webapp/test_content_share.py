"""The explicit share action exposes only the validated destinations."""
from urllib.parse import parse_qs, urlparse
from fastapi import FastAPI
from fastapi.testclient import TestClient

from repositories.explore_repo import ExploreRepository
from services.explore_config import ExploreCatalog, explore_config_loader
from webapp.routers import content
from repositories.content_share_repo import ContentShareRepository
from services import content_share_service
import asyncio
import httpx


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


def test_library_language_filter_is_validated_and_forwarded(monkeypatch):
    calls = []

    class Repo:
        def get_user_contents(self, *_args, **kwargs):
            calls.append(kwargs)
            return []

        def get_user_content_facets(self, *_args, **_kwargs):
            return {"language": {"fr": 2, "unknown": 1}}

    monkeypatch.setattr(content, "get_content_repo", lambda: Repo())
    app = FastAPI()
    app.include_router(content.router)
    app.dependency_overrides[content.get_current_user] = lambda: 7
    with TestClient(app) as client:
        assert client.get("/api/my-contents?language=fr").status_code == 200
        assert client.get("/api/my-contents?language=unknown").status_code == 200
        assert client.get("/api/my-contents?language=fr%27").status_code == 400
    assert [call["language"] for call in calls] == ["fr", "unknown"]


def test_club_share_posts_only_after_reservation_and_records_delivery(monkeypatch):
    calls = []

    class Repo:
        def reserve_club_share(self, content_id, club_id, user_id):
            calls.append(("reserve", content_id, club_id, user_id))
            return {"already_shared": False, "club_name": "French", "chat_id": "-123",
                    "title": "Lesson", "path": "/pdf-reader?content_id=pdf"}

        def finish_club_share(self, content_id, club_id, message_id):
            calls.append(("finish", content_id, club_id, message_id))

        def fail_club_share(self, *_args):
            calls.append(("failed",))

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def post(self, url, json):
            calls.append(("post", url, json))
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 42}})

    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setattr(content_share_service.httpx, "AsyncClient", lambda **_kwargs: Client())
    result = asyncio.run(content_share_service.share_content_with_club("pdf", "club", "7", Repo()))
    assert result["already_shared"] is False
    assert [call[0] for call in calls] == ["reserve", "post", "finish"]
    assert calls[1][2]["chat_id"] == "-123"
    assert calls[1][2]["parse_mode"] == "HTML"
    assert calls[1][2]["text"] == "📚 Lesson"
    assert "\nhttps://" not in calls[1][2]["text"]
    assert parse_qs(urlparse(calls[1][2]["reply_markup"]["inline_keyboard"][0][0]["login_url"]["url"]).query)["next"] == ["/pdf-reader?content_id=pdf"]
    assert calls[2] == ("finish", "pdf", "club", 42)


def test_club_video_share_sends_thumbnail_with_plain_title(monkeypatch):
    calls = []

    class Repo:
        def reserve_club_share(self, *_args):
            return {"already_shared": False, "club_name": "French", "chat_id": "-123",
                    "title": "French & news <today>", "path": "/youtube-watch?video_id=abcdefghijk&club_id=club",
                    "thumbnail_url": "https://img.youtube.com/vi/abcdefghijk/mqdefault.jpg"}

        def finish_club_share(self, *args):
            calls.append(("finish", *args))

        def fail_club_share(self, *_args):
            calls.append(("failed",))

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): pass
        async def post(self, url, **kwargs):
            calls.append(("post", url, kwargs))
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 51}})

    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setattr(content_share_service.httpx, "AsyncClient", lambda **_kwargs: Client())
    asyncio.run(content_share_service.share_content_with_club("video", "club", "7", Repo()))

    assert [call[0] for call in calls] == ["post", "finish"]
    assert calls[0][1].endswith("/sendPhoto")
    photo = calls[0][2]["json"]
    assert photo["photo"] == "https://img.youtube.com/vi/abcdefghijk/mqdefault.jpg"
    assert photo["parse_mode"] == "HTML"
    assert photo["caption"] == "📚 French &amp; news &lt;today&gt;"
    assert "\nhttps://" not in photo["caption"]
    assert parse_qs(urlparse(photo["reply_markup"]["inline_keyboard"][0][0]["login_url"]["url"]).query)["next"] == ["/youtube-watch?video_id=abcdefghijk&club_id=club"]


def test_club_pdf_share_uploads_preview_and_falls_back_if_photo_is_rejected(monkeypatch):
    calls = []

    class Repo:
        def reserve_club_share(self, *_args):
            return {"already_shared": False, "club_name": "French", "chat_id": "-123",
                    "title": "Reader", "path": "/pdf-reader?content_id=pdf&club_id=club",
                    "thumbnail_storage_uri": "local://thumbnail/preview.jpg"}

        def finish_club_share(self, *args):
            calls.append(("finish", *args))

        def fail_club_share(self, *_args):
            calls.append(("failed",))

    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): pass
        async def post(self, url, **kwargs):
            calls.append(("post", url, kwargs))
            if url.endswith("/sendPhoto"):
                return httpx.Response(400, json={"ok": False, "description": "bad photo"})
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 52}})

    async def preview(_client, _uri):
        return b"\xff\xd8preview\xff\xd9"

    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setattr(content_share_service, "_pdf_thumbnail_bytes", preview)
    monkeypatch.setattr(content_share_service.httpx, "AsyncClient", lambda **_kwargs: Client())
    asyncio.run(content_share_service.share_content_with_club("pdf", "club", "7", Repo()))

    assert [call[0] for call in calls] == ["post", "post", "finish"]
    assert calls[0][1].endswith("/sendPhoto")
    assert calls[0][2]["files"]["photo"][1].startswith(b"\xff\xd8")
    assert calls[1][1].endswith("/sendMessage")
    assert calls[1][2]["json"]["parse_mode"] == "HTML"


def test_local_pdf_thumbnail_is_read_for_telegram_upload(monkeypatch, tmp_path):
    preview = tmp_path / "preview.jpg"
    preview.write_bytes(b"\xff\xd8preview\xff\xd9")

    class Storage:
        def resolve_local_storage_uri(self, uri):
            assert uri == "local://thumbnail/preview.jpg"
            return preview

    monkeypatch.setattr(content_share_service, "ObjectStorageService", Storage)
    payload = asyncio.run(content_share_service._pdf_thumbnail_bytes(None, "local://thumbnail/preview.jpg"))
    assert payload == preview.read_bytes()


def test_existing_club_share_does_not_post_again(monkeypatch):
    class Repo:
        def reserve_club_share(self, *_args):
            return {"already_shared": True, "club_name": "French"}

    monkeypatch.delenv("BOT_TOKEN", raising=False)
    result = asyncio.run(content_share_service.share_content_with_club("pdf", "club", "7", Repo()))
    assert result == {"already_shared": True, "club_name": "French"}


def test_club_shelf_is_scoped_to_authenticated_member(monkeypatch):
    calls = []

    def list_for_member(_self, user_id, **kwargs):
        calls.append((user_id, kwargs))
        return [{"content_id": "pdf", "club_id": "club"}]

    monkeypatch.setattr(ContentShareRepository, "list_for_member", list_for_member)
    app = FastAPI()
    app.include_router(content.router)
    app.dependency_overrides[content.get_current_user] = lambda: 7
    with TestClient(app) as client:
        response = client.get("/api/club-shared-content?club_id=club&q=French")
    assert response.status_code == 200
    assert response.json()["items"][0]["content_id"] == "pdf"
    assert calls == [("7", {"club_id": "club", "q": "French", "limit": 31, "offset": 0})]


def test_external_links_never_receive_a_login_handoff():
    keyboard = content_share_service.club_open_keyboard('https://example.org/read', 'Open')
    assert keyboard['inline_keyboard'][0][0] == {'text': 'Open', 'url': 'https://example.org/read'}


def test_login_handoff_is_at_the_site_root_even_with_a_miniapp_path():
    keyboard = content_share_service.club_open_keyboard('/youtube-watch?video_id=abcdefghijk', 'Open', 'https://xaana.club/dashboard')
    url = urlparse(keyboard['inline_keyboard'][0][0]['login_url']['url'])
    assert url.path == '/api/auth/telegram-open'
    assert parse_qs(url.query)['next'] == ['/youtube-watch?video_id=abcdefghijk']
