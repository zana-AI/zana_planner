import io

from pypdf import PdfWriter

from services.pdf_thumbnail_service import ensure_pdf_thumbnail, render_pdf_thumbnail


def _blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_render_pdf_thumbnail_returns_jpeg():
    result = render_pdf_thumbnail(_blank_pdf(), target_width=240)

    assert result.startswith(b"\xff\xd8")
    assert result.endswith(b"\xff\xd9")


def test_ensure_pdf_thumbnail_reuses_same_pdf_revision():
    payload = _blank_pdf()

    class Repo:
        def __init__(self):
            self.asset = None

        def get_latest_content_asset(self, content_id, asset_type):
            return self.asset

        def add_content_asset(self, **kwargs):
            self.asset = {"id": "thumb-1", **kwargs}
            return "thumb-1"

    class Storage:
        calls = 0

        def upload_bytes(self, key, data, content_type):
            self.calls += 1
            assert content_type == "image/jpeg"
            return f"local://{key}", len(data)

    repo = Repo()
    storage = Storage()
    first = ensure_pdf_thumbnail("content-1", payload, content_repo=repo, storage=storage)
    second = ensure_pdf_thumbnail("content-1", payload, content_repo=repo, storage=storage)

    assert first == second == "thumb-1"
    assert storage.calls == 1
