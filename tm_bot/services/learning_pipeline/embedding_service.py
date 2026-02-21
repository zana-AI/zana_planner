"""
Embedding + vector index integration (Vertex embeddings + Qdrant).
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Dict, Iterable, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


class VectorStoreUnavailableError(RuntimeError):
    """Raised when Qdrant is configured but not reachable."""


class EmbeddingService:
    def __init__(
        self,
        qdrant_url: Optional[str] = None,
        qdrant_api_key: Optional[str] = None,
        collection_name: Optional[str] = None,
        embedding_model: Optional[str] = None,
        qdrant_timeout_seconds: float = 10.0,
    ) -> None:
        env_qdrant_url = os.getenv("QDRANT_URL", "").strip()
        env_qdrant_api_key = os.getenv("QDRANT_API_KEY", "").strip() or None
        env_collection = os.getenv("QDRANT_COLLECTION", "content_chunks_v1").strip() or "content_chunks_v1"
        env_embedding_model = (
            os.getenv("VERTEX_EMBEDDING_MODEL", "gemini-embedding-001").strip() or "gemini-embedding-001"
        )

        self.qdrant_url = (qdrant_url if qdrant_url is not None else env_qdrant_url).strip()
        resolved_api_key = qdrant_api_key if qdrant_api_key is not None else env_qdrant_api_key
        if resolved_api_key is None:
            self.qdrant_api_key = None
        else:
            self.qdrant_api_key = str(resolved_api_key).strip() or None
        self.collection_name = (collection_name if collection_name is not None else env_collection).strip() or env_collection
        self.embedding_model = (
            embedding_model if embedding_model is not None else env_embedding_model
        ).strip() or env_embedding_model
        self.qdrant_timeout_seconds = max(1.0, float(qdrant_timeout_seconds))

    def is_configured(self) -> bool:
        return bool(self.qdrant_url)

    def index_chunks(
        self,
        content_id: str,
        chunks: Iterable[Dict[str, Any]],
        language: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> bool:
        chunk_list = [dict(chunk) for chunk in chunks if (chunk.get("text") or "").strip()]
        if not chunk_list:
            return False
        if not self.is_configured():
            logger.warning("Qdrant is not configured (QDRANT_URL missing); skipping vector index")
            return False

        vectors = self.embed_texts([chunk["text"] for chunk in chunk_list])
        if not vectors:
            logger.warning("No embeddings generated; skipping vector index")
            return False
        client, models = self.get_qdrant_client()
        if client is None or models is None:
            raise VectorStoreUnavailableError("Qdrant client is unavailable")

        self.ensure_collection(client, models, vector_size=len(vectors[0]), collection_name=self.collection_name)
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
            if user_id is not None:
                payload["user_id"] = str(user_id)
            raw_id = str(chunk.get("chunk_id") or "")
            try:
                point_id = str(uuid.UUID(raw_id))
            except ValueError:
                point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, raw_id))
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                )
            )
        self.upsert_points(client, points=points, collection_name=self.collection_name, wait=True)
        return True

    def search_chunks(
        self,
        content_id: str,
        query: str,
        limit: int = 8,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not self.is_configured():
            return []
        query = (query or "").strip()
        if not query:
            return []
        query_vectors = self.embed_texts([query])
        if not query_vectors:
            return []
        query_vector = query_vectors[0]
        client, models = self.get_qdrant_client()
        if client is None or models is None:
            raise VectorStoreUnavailableError("Qdrant client is unavailable")

        filter_must = [
            models.FieldCondition(
                key="content_id",
                match=models.MatchValue(value=str(content_id)),
            )
        ]
        if user_id is not None:
            filter_must.append(
                models.FieldCondition(
                    key="user_id",
                    match=models.MatchValue(value=str(user_id)),
                )
            )
        query_filter = models.Filter(must=filter_must)
        hits = self.search_points(
            client=client,
            query_vector=query_vector,
            limit=max(1, int(limit)),
            query_filter=query_filter,
            collection_name=self.collection_name,
        )

        result: List[Dict[str, Any]] = []
        for hit in hits:
            payload = dict(getattr(hit, "payload", {}) or {})
            score = float(getattr(hit, "score", 0.0) or 0.0)
            result.append({"score": score, "payload": payload})
        return result

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return self._embed_texts(texts)

    def get_qdrant_client(self):
        return self._get_qdrant_client()

    def ensure_collection(
        self,
        client,
        models,
        vector_size: int,
        collection_name: Optional[str] = None,
    ) -> None:
        self._ensure_collection(
            client=client,
            models=models,
            vector_size=vector_size,
            collection_name=collection_name or self.collection_name,
        )

    def upsert_points(
        self,
        client,
        points: List[Any],
        collection_name: Optional[str] = None,
        wait: bool = True,
    ) -> None:
        try:
            client.upsert(
                collection_name=collection_name or self.collection_name,
                points=points,
                wait=wait,
            )
        except Exception as exc:
            raise VectorStoreUnavailableError("Qdrant upsert failed") from exc

    def search_points(
        self,
        client,
        query_vector: List[float],
        limit: int = 8,
        query_filter: Any = None,
        collection_name: Optional[str] = None,
    ) -> List[Any]:
        if not query_vector:
            return []
        collection = collection_name or self.collection_name
        max_limit = max(1, int(limit))
        hits: List[Any] = []
        try:
            hits = client.search(
                collection_name=collection,
                query_vector=query_vector,
                limit=max_limit,
                query_filter=query_filter,
            )
        except Exception:
            try:
                response = client.query_points(
                    collection_name=collection,
                    query=query_vector,
                    limit=max_limit,
                    query_filter=query_filter,
                )
                hits = getattr(response, "points", []) or []
            except Exception as exc:
                logger.warning("Qdrant search failed: %s", exc)
                raise VectorStoreUnavailableError("Qdrant search failed") from exc
        return list(hits or [])

    def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            project = os.getenv("GCP_PROJECT_ID", "").strip() or None
            embeddings = GoogleGenerativeAIEmbeddings(
                model=self.embedding_model,
                project=project,
            )
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
            client = QdrantClient(
                url=self.qdrant_url,
                api_key=self.qdrant_api_key,
                timeout=self.qdrant_timeout_seconds,
            )
            return client, models
        except Exception as exc:
            logger.warning("Qdrant client init failed: %s", exc)
            return None, None

    def _ensure_collection(self, client, models, vector_size: int, collection_name: str) -> None:
        try:
            existing = client.get_collection(collection_name)
            if existing:
                return
        except Exception:
            pass
        client.recreate_collection(
            collection_name=collection_name,
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
