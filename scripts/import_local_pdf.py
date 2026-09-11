"""Store one local PDF as a private Xaana Library item.

Run inside zana-webapp with PYTHONPATH=/app/tm_bot. The caller provides a
server-visible PDF path; reruns reuse the content identity and PDF checksum.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--key", required=True, help="Stable Xaana content identity, e.g. edito-b1-2023-livre")
    parser.add_argument("--language", default="fr")
    args = parser.parse_args()

    source = Path(args.file)
    if not source.is_file():
        raise SystemExit(f"PDF not found: {source}")
    payload = source.read_bytes()
    digest = checksum(source)

    from repositories.content_repo import ContentRepository
    from services.object_storage_service import ObjectStorageService

    repo = ContentRepository()
    canonical_url = f"xaana://pdf/{args.key}"
    content_id = repo.upsert_content(
        canonical_url=canonical_url,
        original_url=canonical_url,
        provider="telegram_pdf",
        content_type="text",
        title=args.title,
        language=args.language,
        metadata_json={"mime_type": "application/pdf", "import_key": args.key},
    )
    repo.claim_content_owner(content_id, args.user_id)
    repo.add_user_content(args.user_id, content_id)
    existing = repo.get_latest_content_asset(content_id, "pdf_source")
    if not existing or existing.get("checksum") != digest:
        storage = ObjectStorageService()
        uri, size = storage.upload_pdf_bytes(f"pdf/{args.user_id}/{content_id}/{digest}.pdf", payload)
        asset_id = repo.add_content_asset(content_id, "pdf_source", uri, size, digest)
    else:
        asset_id = str(existing["id"])
    print(f"content_id={content_id} asset_id={asset_id} bytes={len(payload)}")


if __name__ == "__main__":
    main()
