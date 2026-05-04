"""
S3-compatible object storage service for storing immutable PDF binaries.
"""
from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import boto3
from botocore.client import Config


class ObjectStorageService:
    def __init__(self) -> None:
        self.endpoint_url = (os.getenv("OBJECT_STORAGE_ENDPOINT") or "").strip() or None
        self.region = (os.getenv("OBJECT_STORAGE_REGION") or "us-east-1").strip()
        self.bucket = (os.getenv("OBJECT_STORAGE_BUCKET") or "").strip()
        self.access_key = (os.getenv("OBJECT_STORAGE_ACCESS_KEY_ID") or "").strip()
        self.secret_key = (os.getenv("OBJECT_STORAGE_SECRET_ACCESS_KEY") or "").strip()
        self.presign_ttl = int(os.getenv("OBJECT_STORAGE_SIGNED_URL_TTL_SECONDS") or "600")
        self.local_dir = self._default_local_dir()

        self._client = None
        if self.mode == "s3":
            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                region_name=self.region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
            )
        elif self.mode == "local":
            self.local_dir.mkdir(parents=True, exist_ok=True)

    @property
    def mode(self) -> str:
        if self.bucket and self.access_key and self.secret_key:
            return "s3"
        return "local"

    @property
    def is_configured(self) -> bool:
        if self.mode == "s3":
            return True
        return bool(self.local_dir)

    def _require_client(self):
        if not self._client:
            raise RuntimeError("Object storage is not configured")
        return self._client

    def upload_pdf_bytes(self, key: str, payload: bytes) -> Tuple[str, Optional[int]]:
        """
        Upload PDF bytes and return storage URI + ETag length.
        """
        normalized_key = key.strip("/").replace("\\", "/")
        if self.mode == "s3":
            client = self._require_client()
            client.put_object(
                Bucket=self.bucket,
                Key=normalized_key,
                Body=payload,
                ContentType="application/pdf",
            )
            return f"s3://{self.bucket}/{normalized_key}", len(payload)

        local_path = self._resolve_local_key_to_path(normalized_key)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(payload)
        return f"local://{normalized_key}", len(payload)

    def build_signed_get_url(self, storage_uri: str, expires_in: Optional[int] = None) -> Tuple[str, str]:
        """
        Return signed URL and ISO expiry timestamp.
        """
        if storage_uri.startswith("local://"):
            raise RuntimeError("Local storage URIs must be served through the API file endpoint")

        client = self._require_client()
        bucket, key = self._parse_storage_uri(storage_uri)
        ttl = int(expires_in or self.presign_ttl)
        url = client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=ttl,
        )
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat()
        return url, expires_at

    def build_local_file_url(self, content_id: str, asset_id: str) -> str:
        return f"/api/content/{content_id}/pdf/file?asset_id={asset_id}"

    def resolve_local_storage_uri(self, storage_uri: str) -> Path:
        if not storage_uri.startswith("local://"):
            raise ValueError("Expected local:// storage URI")
        key = storage_uri[len("local://") :]
        if not key:
            raise ValueError("Invalid local storage URI")
        return self._resolve_local_key_to_path(key)

    def _resolve_local_key_to_path(self, key: str) -> Path:
        normalized = key.strip("/").replace("\\", "/")
        candidate = (self.local_dir / normalized).resolve()
        try:
            if os.path.commonpath([str(candidate), str(self.local_dir)]) != str(self.local_dir):
                raise ValueError("Invalid object key path traversal")
        except ValueError:
            raise ValueError("Invalid object key path traversal")
        return candidate

    @staticmethod
    def _default_local_dir() -> Path:
        configured = os.getenv("OBJECT_STORAGE_LOCAL_DIR") or os.getenv("PDF_LOCAL_STORAGE_DIR")
        if configured and configured.strip():
            return Path(configured.strip()).resolve()

        root_dir = os.getenv("ROOT_DIR")
        if root_dir and root_dir.strip():
            return (Path(root_dir.strip()) / "_content_assets" / "pdf").resolve()

        return (Path.cwd() / "USERS_DATA_DIR" / "_content_assets" / "pdf").resolve()

    @staticmethod
    def _parse_storage_uri(storage_uri: str) -> Tuple[str, str]:
        if not storage_uri or not storage_uri.startswith("s3://"):
            raise ValueError("Invalid storage_uri (expected s3://bucket/key)")
        path = storage_uri[len("s3://") :]
        if "/" not in path:
            raise ValueError("Invalid storage_uri (missing key)")
        bucket, key = path.split("/", 1)
        if not bucket or not key:
            raise ValueError("Invalid storage_uri")
        return bucket, key
