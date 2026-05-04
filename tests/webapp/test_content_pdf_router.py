import asyncio
from pathlib import Path

import httpx
from fastapi import FastAPI

from webapp.dependencies import get_current_user
from webapp.routers import content as content_router


class FakeRepo:
    def __init__(self):
        self.highlights = []
        self._seq = 0

    def get_user_content(self, user_id, content_id):
        if str(content_id) != "content-1":
            return None
        return {
            "user_id": str(user_id),
            "content_id": str(content_id),
            "last_position": 0.25,
            "progress_ratio": 0.25,
        }

    def get_latest_content_asset(self, content_id, asset_type):
        if str(content_id) != "content-1" or asset_type != "pdf_source":
            return None
        return {"id": "asset-1", "content_id": "content-1", "storage_uri": "s3://bucket/k1"}

    def get_content_asset(self, content_id, asset_id):
        if str(content_id) == "content-1" and str(asset_id) == "asset-1":
            return {"id": "asset-1", "content_id": "content-1", "storage_uri": "s3://bucket/k1"}
        return None

    def list_highlights(self, user_id, content_id, asset_id):
        return [
            h for h in self.highlights
            if h["user_id"] == str(user_id) and h["content_id"] == str(content_id) and h["asset_id"] == str(asset_id)
        ]

    def create_highlight(self, user_id, content_id, asset_id, page_index, rects, selected_text=None, note=None, color=None, copied_from_highlight_id=None, migration_status=None):
        self._seq += 1
        hid = f"h-{self._seq}"
        item = {
            "id": hid,
            "user_id": str(user_id),
            "content_id": str(content_id),
            "asset_id": str(asset_id),
            "page_index": int(page_index),
            "rects_json": rects or [],
            "selected_text": selected_text,
            "note": note,
            "color": color,
            "created_at": "2026-05-04T00:00:00Z",
            "updated_at": "2026-05-04T00:00:00Z",
            "copied_from_highlight_id": copied_from_highlight_id,
            "migration_status": migration_status,
        }
        self.highlights.append(item)
        return hid

    def get_highlight(self, user_id, content_id, highlight_id):
        for item in self.highlights:
            if item["id"] == str(highlight_id) and item["user_id"] == str(user_id) and item["content_id"] == str(content_id):
                return item
        return None

    def update_highlight(self, user_id, content_id, highlight_id, rects=None, selected_text=None, note=None, color=None):
        for item in self.highlights:
            if item["id"] == str(highlight_id) and item["user_id"] == str(user_id) and item["content_id"] == str(content_id):
                if rects is not None:
                    item["rects_json"] = rects
                if selected_text is not None:
                    item["selected_text"] = selected_text
                if note is not None:
                    item["note"] = note
                if color is not None:
                    item["color"] = color
                return True
        return False

    def delete_highlight(self, user_id, content_id, highlight_id):
        before = len(self.highlights)
        self.highlights = [
            h for h in self.highlights
            if not (h["id"] == str(highlight_id) and h["user_id"] == str(user_id) and h["content_id"] == str(content_id))
        ]
        return len(self.highlights) < before


class FakeStorage:
    def build_signed_get_url(self, storage_uri: str):
        assert storage_uri == "s3://bucket/k1"
        return "https://signed.example/pdf", "2026-05-04T12:00:00Z"

    def build_local_file_url(self, content_id: str, asset_id: str):
        return f"/api/content/{content_id}/pdf/file?asset_id={asset_id}"


class LocalRepo(FakeRepo):
    def __init__(self, local_uri: str):
        super().__init__()
        self.local_uri = local_uri

    def get_latest_content_asset(self, content_id, asset_type):
        if str(content_id) != "content-1" or asset_type != "pdf_source":
            return None
        return {"id": "asset-1", "content_id": "content-1", "storage_uri": self.local_uri}

    def get_content_asset(self, content_id, asset_id):
        if str(content_id) == "content-1" and str(asset_id) == "asset-1":
            return {"id": "asset-1", "content_id": "content-1", "storage_uri": self.local_uri}
        return None


class LocalStorage:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.presign_ttl = 600

    def build_local_file_url(self, content_id: str, asset_id: str):
        return f"/api/content/{content_id}/pdf/file?asset_id={asset_id}"

    def resolve_local_storage_uri(self, storage_uri: str):
        assert storage_uri.startswith("local://")
        return self.file_path


class _ASGITestClient:
    def __init__(self, app, base_url: str = "http://testserver"):
        self._app = app
        self._base_url = base_url

    def _request(self, method: str, url: str, **kwargs):
        async def _run():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self._app),
                base_url=self._base_url,
            ) as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(_run())

    def get(self, url: str, **kwargs):
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self._request("POST", url, **kwargs)

    def patch(self, url: str, **kwargs):
        return self._request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs):
        return self._request("DELETE", url, **kwargs)


def TestClient(app, base_url: str = "http://testserver"):
    return _ASGITestClient(app, base_url)


def _build_app(monkeypatch):
    app = FastAPI()
    app.include_router(content_router.router)
    app.dependency_overrides[get_current_user] = lambda: 7
    fake_repo = FakeRepo()
    monkeypatch.setattr(content_router, "get_content_repo", lambda: fake_repo)
    monkeypatch.setattr(content_router, "get_object_storage_service", lambda: FakeStorage())
    return app, fake_repo


def _build_local_app(monkeypatch, file_path: Path):
    app = FastAPI()
    app.include_router(content_router.router)
    app.dependency_overrides[get_current_user] = lambda: 7
    fake_repo = LocalRepo(local_uri="local://pdf/7/content-1/v1.pdf")
    monkeypatch.setattr(content_router, "get_content_repo", lambda: fake_repo)
    monkeypatch.setattr(content_router, "get_object_storage_service", lambda: LocalStorage(file_path))
    return app, fake_repo


def test_get_pdf_open_returns_signed_url(monkeypatch):
    app, _ = _build_app(monkeypatch)
    client = TestClient(app)

    response = client.get("/api/content/content-1/pdf")
    assert response.status_code == 200
    body = response.json()
    assert body["content_id"] == "content-1"
    assert body["asset_id"] == "asset-1"
    assert body["pdf_url"] == "https://signed.example/pdf"
    assert body["progress_ratio"] == 0.25


def test_pdf_highlight_crud(monkeypatch):
    app, _ = _build_app(monkeypatch)
    client = TestClient(app)

    create = client.post(
        "/api/content/content-1/highlights",
        json={
            "asset_id": "asset-1",
            "page_index": 2,
            "rects": [{"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1}],
            "selected_text": "hello",
            "note": "note",
            "color": "#ffee00",
        },
    )
    assert create.status_code == 200
    highlight_id = create.json()["highlight_id"]

    listed = client.get("/api/content/content-1/highlights?asset_id=asset-1")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1

    patched = client.patch(
        f"/api/content/content-1/highlights/{highlight_id}",
        json={"note": "updated note"},
    )
    assert patched.status_code == 200
    assert patched.json()["updated"] is True

    deleted = client.delete(f"/api/content/content-1/highlights/{highlight_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True


def test_local_pdf_open_and_file(monkeypatch, tmp_path):
    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"%PDF-1.7 local test")
    app, _ = _build_local_app(monkeypatch, file_path=file_path)
    client = TestClient(app)

    opened = client.get("/api/content/content-1/pdf")
    assert opened.status_code == 200
    body = opened.json()
    assert body["pdf_url"] == "/api/content/content-1/pdf/file?asset_id=asset-1"
    assert body["asset_id"] == "asset-1"

    file_resp = client.get("/api/content/content-1/pdf/file?asset_id=asset-1")
    assert file_resp.status_code == 200
    assert file_resp.content == b"%PDF-1.7 local test"
    assert file_resp.headers["content-type"].startswith("application/pdf")
