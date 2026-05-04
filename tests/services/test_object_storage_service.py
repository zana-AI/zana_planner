from datetime import datetime

import pytest

from services.object_storage_service import ObjectStorageService


class _FakeS3Client:
    def __init__(self):
        self.put_calls = []
        self.presign_calls = []

    def put_object(self, **kwargs):
        self.put_calls.append(kwargs)

    def generate_presigned_url(self, ClientMethod, Params, ExpiresIn):
        self.presign_calls.append(
            {
                "client_method": ClientMethod,
                "params": Params,
                "expires_in": ExpiresIn,
            }
        )
        return f"https://signed.example/{Params['Bucket']}/{Params['Key']}?exp={ExpiresIn}"


def test_upload_and_sign(monkeypatch):
    fake_client = _FakeS3Client()
    monkeypatch.setenv("OBJECT_STORAGE_BUCKET", "xaana-pdf")
    monkeypatch.setenv("OBJECT_STORAGE_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("OBJECT_STORAGE_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("OBJECT_STORAGE_SIGNED_URL_TTL_SECONDS", "600")
    monkeypatch.setattr("services.object_storage_service.boto3.client", lambda *args, **kwargs: fake_client)

    svc = ObjectStorageService()
    assert svc.is_configured is True

    uri, size_bytes = svc.upload_pdf_bytes("pdf/user/content/v1.pdf", b"%PDF-1.7")
    assert uri == "s3://xaana-pdf/pdf/user/content/v1.pdf"
    assert size_bytes == 8
    assert fake_client.put_calls[0]["ContentType"] == "application/pdf"

    url, expires_at = svc.build_signed_get_url(uri, expires_in=120)
    assert url == "https://signed.example/xaana-pdf/pdf/user/content/v1.pdf?exp=120"
    assert fake_client.presign_calls[0]["client_method"] == "get_object"
    assert fake_client.presign_calls[0]["params"] == {"Bucket": "xaana-pdf", "Key": "pdf/user/content/v1.pdf"}
    assert fake_client.presign_calls[0]["expires_in"] == 120
    assert datetime.fromisoformat(expires_at)


def test_invalid_storage_uri_raises():
    with pytest.raises(ValueError):
        ObjectStorageService._parse_storage_uri("https://example.com/file.pdf")


def test_local_mode_upload_and_resolve(monkeypatch, tmp_path):
    monkeypatch.delenv("OBJECT_STORAGE_BUCKET", raising=False)
    monkeypatch.delenv("OBJECT_STORAGE_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("OBJECT_STORAGE_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.setenv("OBJECT_STORAGE_LOCAL_DIR", str(tmp_path / "pdf-store"))

    svc = ObjectStorageService()
    assert svc.mode == "local"
    uri, size_bytes = svc.upload_pdf_bytes("pdf/1/content-x/v2.pdf", b"hello-pdf")
    assert uri == "local://pdf/1/content-x/v2.pdf"
    assert size_bytes == 9

    resolved = svc.resolve_local_storage_uri(uri)
    assert resolved.exists()
    assert resolved.read_bytes() == b"hello-pdf"


def test_local_default_uses_root_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("OBJECT_STORAGE_BUCKET", raising=False)
    monkeypatch.delenv("OBJECT_STORAGE_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("OBJECT_STORAGE_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("OBJECT_STORAGE_LOCAL_DIR", raising=False)
    monkeypatch.delenv("PDF_LOCAL_STORAGE_DIR", raising=False)
    monkeypatch.setenv("ROOT_DIR", str(tmp_path / "users"))

    svc = ObjectStorageService()
    assert svc.local_dir == (tmp_path / "users" / "_content_assets" / "pdf").resolve()


def test_local_path_traversal_rejected(monkeypatch, tmp_path):
    monkeypatch.delenv("OBJECT_STORAGE_BUCKET", raising=False)
    monkeypatch.delenv("OBJECT_STORAGE_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("OBJECT_STORAGE_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.setenv("OBJECT_STORAGE_LOCAL_DIR", str(tmp_path / "pdf-store"))

    svc = ObjectStorageService()
    with pytest.raises(ValueError):
        svc.resolve_local_storage_uri("local://../outside.pdf")
