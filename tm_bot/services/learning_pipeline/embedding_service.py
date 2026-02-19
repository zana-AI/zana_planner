"""
Embedding + vector index integration (Vertex embeddings + Qdrant).
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


class VectorStoreUnavailableError(RuntimeError):
    """Raised when Qdrant is configured but not reachable."""


class EmbeddingService:
    def __init__(self) -> None:
        self.qdrant_url = os.getenv("QDRANT_URL", "").strip()
        self.qdrant_api_key = os.getenv("QDRANT_API_KEY", "").strip() or None
        self.collection_name = os.getenv("QDRANT_COLLECTION", "content_chunks_v1").strip() or "content_chunks_v1"
        self.embedding_model = os.getenv("VERTEX_EMBEDDING_MODEL", "gemini-embedding-001").strip() or "gemini-embedding-001"

    def is_configured(self) -> bool:
        return bool(self.qdrant_url)

    def index_chunks(
        self,
        content_id: str,
        chunks: Iterable[Dict[str, Any]],
        language: Optional[str] = None,
    ) -> bool:
        chunk_list = [dict(chunk) for chunk in chunks if (chunk.get("text") or "").strip()]
        if not chunk_list:
            return False
        if not self.is_configured():
            logger.warning("Qdrant is not configured (QDRANT_URL missing); skipping vector index")
            return False

        vectors = self._embed_texts([chunk["text"] for chunk in chunk_list])
        if not vectors:
            logger.warning("No embeddings generated; skipping vector index")
            return False
        client, models = self._get_qdrant_client()
        if client is None or models is None:
            raise VectorStoreUnavailableError("Qdrant client is unavailable")

        self._ensure_collection(client, models, vector_size=len(vectors[0]))
        points = []
        for chunk, vector in zip(chunk_list, vectors):
            payload = {
                "content_id": str(content_id),
                "segment_id": str(chunk.get("segment_id") or ""),
                "segment_index": chunk.get("segment_index"),
                "chunk_index": chunk.get("chunk_index"),
                "start_ms": chunk.get("start_ms"),
                "end_ms": chunk.get("end_ms"),
                "section_path": chunk.get("section_path"),
                "language": language,
                "text": chunk.get("text"),
                "source_type": chunk.get("source_type"),
                "concept_ids": chunk.get("concept_ids") or [],
            }
            points.append(
                models.PointStruct(
                    id=str(chunk.get("chunk_id")),
                    vector=vector,
                    payload=payload,
                )
            )
        try:
            client.upsert(collection_name=self.collection_name, points=points, wait=True)
        except Exception as exc:
            raise VectorStoreUnavailableError("Qdrant upsert failed") from exc
        return True

    def search_chunks(self, content_id: str, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        if not self.is_configured():
            return []
        query = (query or "").strip()
        if not query:
            return []
        query_vectors = self._embed_texts([query])
        if not query_vectors:
            return []
        query_vector = query_vectors[0]
        client, models = self._get_qdrant_client()
        if client is None or models is None:
            raise VectorStoreUnavailableError("Qdrant client is unavailable")

        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="content_id",
                    match=models.MatchValue(value=str(content_id)),
                )
            ]
        )
        hits: List[Any] = []
        try:
            hits = client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=max(1, int(limit)),
                query_filter=query_filter,
            )
        except Exception:
            try:
                response = client.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    limit=max(1, int(limit)),
                    query_filter=query_filter,
                )
                hits = getattr(response, "points", []) or []
            except Exception as exc:
                logger.warning("Qdrant search failed: %s", exc)
                raise VectorStoreUnavailableError("Qdrant search failed") from exc

        result: List[Dict[str, Any]] = []
        for hit in hits:
            payload = dict(getattr(hit, "payload", {}) or {})
            score = float(getattr(hit, "score", 0.0) or 0.0)
            result.append({"score": score, "payload": payload})
        return result

    def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        try:
            from langchain_google_vertexai import VertexAIEmbeddings
            embeddings = VertexAIEmbeddings(model_name=self.embedding_model)
            return embeddings.embed_documents(texts)
        except Exception as exc:
            logger.warning("Vertex embedding failed (%s), falling back to deterministic embedding", exc)
            return [_deterministic_vector(text) for text in texts]

    def _get_qdrant_client(self):
        try:
            from qdrant_client import QdrantClient, models
        except Exception:
            return None, None
        try:
            client = QdrantClient(url=self.qdrant_url, api_key=self.qdrant_api_key, timeout=10.0)
            return client, models
        except Exception as exc:
            logger.warning("Qdrant client init failed: %s", exc)
            return None, None

    def _ensure_collection(self, client, models, vector_size: int) -> None:
        try:
            existing = client.get_collection(self.collection_name)
            if existing:
                return
        except Exception:
            pass
        client.recreate_collection(
            collection_name=self.collection_name,
            vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
        )


def _deterministic_vector(text: str, size: int = 256) -> List[float]:
    values = [0.0] * size
    raw = (text or "").encode("utf-8")
    if not raw:
        return values
    for idx, byte in enumerate(raw):
        pos = idx % size
        values[pos] += float((byte - 127) / 255.0)
    norm = sum(abs(v) for v in values) or 1.0
    return [v / norm for v in values]
