"""
Semantic memory search with Qdrant-first retrieval and filesystem fallback.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from memory.config import (
    get_memory_collection_name,
    get_memory_embedding_model,
    get_memory_root,
    get_memory_vector_db_api_key,
    get_memory_vector_db_url,
    is_memory_configured,
)
from services.learning_pipeline.embedding_service import EmbeddingService, VectorStoreUnavailableError
from utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_MAX_RESULTS = 6
_DEFAULT_MIN_SCORE = 0.25
_DEFAULT_CHUNK_LINES = 14
_DEFAULT_CHUNK_OVERLAP = 3
_DEFAULT_CHUNK_MAX_CHARS = 900
_DEFAULT_SNIPPET_MAX_CHARS = 380
_MANIFEST_FILE = ".memory_index_manifest.json"
_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]{2,}")


@dataclass(frozen=True)
class _MemoryChunk:
    rel_path: str
    start_line: int
    end_line: int
    text: str


def memory_search(
    query: str,
    root_dir: str,
    user_id: str,
    max_results: Optional[int] = None,
    min_score: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Search this user's MEMORY.md and memory/*.md.

    Strategy:
    1) If vector backend is configured and reachable, search Qdrant (user-scoped filter).
    2) If vector backend is unavailable or empty, fall back to local keyword retrieval.
    """
    cleaned_query = (query or "").strip()
    if not cleaned_query:
        return {"results": [], "disabled": False, "backend": "none", "error": "query is required"}

    limit = _coerce_positive_int(max_results, default=_DEFAULT_MAX_RESULTS)
    threshold = _coerce_score(min_score, default=_DEFAULT_MIN_SCORE)

    try:
        memory_root = get_memory_root(root_dir, user_id)
    except ValueError as exc:
        return {"results": [], "disabled": True, "backend": "none", "error": str(exc)}

    vector_error: Optional[str] = None
    if is_memory_configured():
        try:
            vector_results = _search_with_qdrant(
                query=cleaned_query,
                memory_root=memory_root,
                user_id=str(user_id),
                max_results=limit,
                min_score=threshold,
            )
            if vector_results:
                return {
                    "results": vector_results,
                    "disabled": False,
                    "backend": "qdrant",
                    "fallback_used": False,
                    "error": None,
                }
        except Exception as exc:  # pragma: no cover - defensive, runtime-dependent
            vector_error = str(exc)
            logger.warning("memory_search vector retrieval failed for user %s: %s", user_id, exc)

    fallback_results = _search_local_keyword(
        query=cleaned_query,
        memory_root=memory_root,
        max_results=limit,
        min_score=threshold,
    )
    return {
        "results": fallback_results,
        "disabled": False,
        "backend": "filesystem",
        "fallback_used": True,
        "error": vector_error,
    }


def _search_with_qdrant(
    query: str,
    memory_root: Path,
    user_id: str,
    max_results: int,
    min_score: float,
) -> List[Dict[str, Any]]:
    service = EmbeddingService(
        qdrant_url=get_memory_vector_db_url(),
        qdrant_api_key=get_memory_vector_db_api_key() or None,
        collection_name=get_memory_collection_name(),
        embedding_model=get_memory_embedding_model(),
    )
    if not service.is_configured():
        return []

    client, models = service.get_qdrant_client()
    if client is None or models is None:
        raise VectorStoreUnavailableError("Qdrant client is unavailable")

    _sync_user_memory_index(
        service=service,
        client=client,
        models=models,
        memory_root=memory_root,
        user_id=user_id,
    )

    vectors = service.embed_texts([query])
    if not vectors:
        return []
    query_vector = vectors[0]

    query_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="user_id",
                match=models.MatchValue(value=str(user_id)),
            )
        ]
    )
    hits = service.search_points(
        client=client,
        query_vector=query_vector,
        limit=max_results,
        query_filter=query_filter,
        collection_name=get_memory_collection_name(),
    )

    results: List[Dict[str, Any]] = []
    for hit in hits:
        payload = dict(getattr(hit, "payload", {}) or {})
        score = float(getattr(hit, "score", 0.0) or 0.0)
        if score < min_score:
            continue
        snippet = str(payload.get("text") or "").strip()
        if not snippet:
            continue
        results.append(
            {
                "path": str(payload.get("path") or ""),
                "start_line": int(payload.get("start_line") or 1),
                "end_line": int(payload.get("end_line") or 1),
                "score": round(score, 6),
                "snippet": _truncate(snippet, _DEFAULT_SNIPPET_MAX_CHARS),
                "source": "vector",
            }
        )

    results.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    return results[:max_results]


def _sync_user_memory_index(
    service: EmbeddingService,
    client: Any,
    models: Any,
    memory_root: Path,
    user_id: str,
) -> None:
    collection_name = get_memory_collection_name()
    files = _collect_memory_files(memory_root)
    current_manifest = {
        rel_path: _file_fingerprint(path)
        for rel_path, path in files.items()
    }

    manifest_path = memory_root / _MANIFEST_FILE
    previous_manifest = _load_manifest(manifest_path)

    removed_paths = [rel for rel in previous_manifest.keys() if rel not in current_manifest]
    changed_paths = [
        rel for rel, fingerprint in current_manifest.items()
        if previous_manifest.get(rel) != fingerprint
    ]

    if not removed_paths and not changed_paths:
        return

    for rel_path in removed_paths:
        _delete_points_for_path(
            client=client,
            models=models,
            collection_name=collection_name,
            user_id=user_id,
            rel_path=rel_path,
        )

    collection_ready = False
    for rel_path in changed_paths:
        _delete_points_for_path(
            client=client,
            models=models,
            collection_name=collection_name,
            user_id=user_id,
            rel_path=rel_path,
        )

        full_path = files.get(rel_path)
        if full_path is None:
            continue
        chunks = _chunk_file(full_path, rel_path)
        if not chunks:
            continue
        vectors = service.embed_texts([chunk.text for chunk in chunks])
        if not vectors:
            continue
        if not collection_ready:
            service.ensure_collection(
                client=client,
                models=models,
                vector_size=len(vectors[0]),
                collection_name=collection_name,
            )
            collection_ready = True

        points = []
        for chunk, vector in zip(chunks, vectors):
            payload = {
                "user_id": str(user_id),
                "path": chunk.rel_path,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "text": chunk.text,
            }
            points.append(
                models.PointStruct(
                    id=_point_id(user_id, chunk),
                    vector=vector,
                    payload=payload,
                )
            )
        if points:
            service.upsert_points(
                client=client,
                points=points,
                collection_name=collection_name,
                wait=True,
            )

    _write_manifest(manifest_path, current_manifest)


def _search_local_keyword(
    query: str,
    memory_root: Path,
    max_results: int,
    min_score: float,
) -> List[Dict[str, Any]]:
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    scored: List[Dict[str, Any]] = []
    for rel_path, full_path in _collect_memory_files(memory_root).items():
        for chunk in _chunk_file(full_path, rel_path):
            score = _keyword_score(query_tokens, query, chunk.text)
            if score < min_score:
                continue
            scored.append(
                {
                    "path": chunk.rel_path,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "score": round(score, 6),
                    "snippet": _truncate(chunk.text, _DEFAULT_SNIPPET_MAX_CHARS),
                    "source": "keyword",
                }
            )

    scored.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    return scored[:max_results]


def _collect_memory_files(memory_root: Path) -> Dict[str, Path]:
    files: Dict[str, Path] = {}
    memory_md = memory_root / "MEMORY.md"
    if memory_md.is_file():
        files["MEMORY.md"] = memory_md

    memory_dir = memory_root / "memory"
    if memory_dir.is_dir():
        for file_path in sorted(memory_dir.rglob("*.md")):
            if not file_path.is_file():
                continue
            try:
                rel_path = file_path.resolve().relative_to(memory_root.resolve()).as_posix()
            except Exception:
                continue
            files[rel_path] = file_path
    return files


def _chunk_file(path: Path, rel_path: str) -> List[_MemoryChunk]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if not text.strip():
        return []

    lines = text.splitlines()
    chunks: List[_MemoryChunk] = []
    start = 0
    chunk_size = max(2, _DEFAULT_CHUNK_LINES)
    overlap = max(0, min(_DEFAULT_CHUNK_OVERLAP, chunk_size - 1))

    while start < len(lines):
        end = min(len(lines), start + chunk_size)
        chunk_text = "\n".join(lines[start:end]).strip()
        if chunk_text:
            chunks.append(
                _MemoryChunk(
                    rel_path=rel_path,
                    start_line=start + 1,
                    end_line=end,
                    text=_truncate(chunk_text, _DEFAULT_CHUNK_MAX_CHARS),
                )
            )
        if end >= len(lines):
            break
        start = max(start + 1, end - overlap)

    return chunks


def _point_id(user_id: str, chunk: _MemoryChunk) -> str:
    payload = f"{user_id}|{chunk.rel_path}|{chunk.start_line}|{chunk.end_line}|{chunk.text}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _delete_points_for_path(
    client: Any,
    models: Any,
    collection_name: str,
    user_id: str,
    rel_path: str,
) -> None:
    file_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="user_id",
                match=models.MatchValue(value=str(user_id)),
            ),
            models.FieldCondition(
                key="path",
                match=models.MatchValue(value=rel_path),
            ),
        ]
    )
    try:
        client.delete(
            collection_name=collection_name,
            points_selector=models.FilterSelector(filter=file_filter),
            wait=True,
        )
        return
    except Exception:
        pass
    try:
        client.delete(
            collection_name=collection_name,
            points_selector=file_filter,
            wait=True,
        )
    except Exception as exc:  # pragma: no cover - API version differences
        logger.debug("memory_search: delete points failed for %s: %s", rel_path, exc)


def _file_fingerprint(path: Path) -> str:
    try:
        stat = path.stat()
        return f"{stat.st_size}:{stat.st_mtime_ns}"
    except OSError:
        return "missing"


def _load_manifest(path: Path) -> Dict[str, str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    files = raw.get("files")
    if not isinstance(files, dict):
        return {}
    out: Dict[str, str] = {}
    for rel_path, fingerprint in files.items():
        if isinstance(rel_path, str) and isinstance(fingerprint, str):
            out[rel_path] = fingerprint
    return out


def _write_manifest(path: Path, files: Dict[str, str]) -> None:
    payload = {
        "version": 1,
        "files": files,
    }
    try:
        path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    except OSError as exc:  # pragma: no cover - non-fatal
        logger.debug("memory_search: failed to write manifest %s: %s", path, exc)


def _tokenize(text: str) -> List[str]:
    return [tok.lower() for tok in _TOKEN_RE.findall(text or "")]


def _keyword_score(query_tokens: List[str], raw_query: str, text: str) -> float:
    lowered = (text or "").lower()
    if not lowered:
        return 0.0

    unique_tokens = sorted(set(query_tokens))
    token_hits = sum(1 for token in unique_tokens if token in lowered)
    coverage = token_hits / max(1, len(unique_tokens))

    phrase = (raw_query or "").strip().lower()
    phrase_boost = 0.25 if phrase and phrase in lowered else 0.0

    text_tokens = set(_tokenize(lowered))
    density = token_hits / max(1, len(text_tokens))
    density = min(1.0, density * 4.0)

    return min(1.0, phrase_boost + (coverage * 0.6) + (density * 0.4))


def _truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)] + "..."


def _coerce_positive_int(value: Optional[int], default: int) -> int:
    if value is None:
        return default
    try:
        return max(1, int(value))
    except Exception:
        return default


def _coerce_score(value: Optional[float], default: float) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
    except Exception:
        return default
    return max(0.0, min(1.0, parsed))
