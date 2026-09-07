"""Small, best-effort first-page previews for PDF content cards."""
from __future__ import annotations

import hashlib
import io
import uuid
from typing import Optional

from repositories.content_repo import ContentRepository
from services.object_storage_service import ObjectStorageService


PDF_THUMBNAIL_ASSET_TYPE = "pdf_thumbnail"


def render_pdf_thumbnail(payload: bytes, target_width: int = 420) -> bytes:
    """Render page one as a compact JPEG without changing the source PDF."""
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(payload)
    try:
        if len(document) < 1:
            raise ValueError("PDF has no pages")
        page = document[0]
        try:
            width, _height = page.get_size()
            scale = max(0.25, min(3.0, float(target_width) / max(float(width), 1.0)))
            bitmap = page.render(scale=scale)
            try:
                image = bitmap.to_pil().convert("RGB")
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=82, optimize=True, progressive=True)
                return output.getvalue()
            finally:
                bitmap.close()
        finally:
            page.close()
    finally:
        document.close()


def ensure_pdf_thumbnail(
    content_id: str,
    payload: bytes,
    *,
    content_repo: Optional[ContentRepository] = None,
    storage: Optional[ObjectStorageService] = None,
) -> str:
    """Create one thumbnail asset unless this PDF revision already has one."""
    repo = content_repo or ContentRepository()
    existing = repo.get_latest_content_asset(content_id, PDF_THUMBNAIL_ASSET_TYPE)
    source_checksum = hashlib.sha256(payload).hexdigest()
    if existing and str(existing.get("checksum") or "") == source_checksum:
        return str(existing["id"])

    thumbnail = render_pdf_thumbnail(payload)
    object_key = f"thumbnail/{content_id}/{uuid.uuid4().hex}_{source_checksum[:12]}.jpg"
    storage_service = storage or ObjectStorageService()
    storage_uri, size_bytes = storage_service.upload_bytes(
        object_key,
        thumbnail,
        content_type="image/jpeg",
    )
    return repo.add_content_asset(
        content_id=content_id,
        asset_type=PDF_THUMBNAIL_ASSET_TYPE,
        storage_uri=storage_uri,
        size_bytes=size_bytes,
        checksum=source_checksum,
    )
