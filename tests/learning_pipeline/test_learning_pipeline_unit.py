import math

import pytest

from services.learning_pipeline.analysis_service import _compute_weights
from services.learning_pipeline.embedding_service import EmbeddingService
from services.learning_pipeline.learning_repo import compute_next_mastery_score
from services.learning_pipeline.security import validate_safe_http_url
from services.learning_pipeline.segmenter import Segmenter


def test_segmenter_splits_and_chunks_text():
    segmenter = Segmenter(chunk_size=120, chunk_overlap=20)
    text = ("This is a paragraph about learning systems. " * 20) + "\n\n" + ("Another paragraph about quizzes. " * 15)
    segments = segmenter.segment_text(text, section_path="article")
    assert len(segments) >= 2
    assert all(segment.text for segment in segments)

    segment_rows = []
    for idx, segment in enumerate(segments):
        segment_rows.append(
            {
                "id": f"seg-{idx}",
                "segment_index": idx,
                "text": segment.text,
                "start_ms": None,
                "end_ms": None,
                "section_path": segment.section_path,
            }
        )
    chunks = segmenter.build_chunks(segment_rows)
    assert chunks
    assert all(chunk["text"] for chunk in chunks)


def test_compute_weights_returns_normalized_values():
    concepts = [
        {"label": "python", "concept_type": "topic", "definition": "", "examples": []},
        {"label": "graph", "concept_type": "topic", "definition": "", "examples": []},
        {"label": "quiz", "concept_type": "topic", "definition": "", "examples": []},
    ]
    edges = [
        {"source": "python", "target": "graph", "relation_type": "used_for", "confidence": 0.9, "weight": 0.9},
        {"source": "graph", "target": "quiz", "relation_type": "explains", "confidence": 0.6, "weight": 0.6},
    ]
    segments = [
        {"text": "python graph python quiz"},
        {"text": "graph based quiz and python applications"},
    ]
    weighted = _compute_weights(concepts, edges, segments)
    assert len(weighted) == 3
    weights = [item["importance_weight"] for item in weighted]
    assert all(0.0 <= value <= 1.0 for value in weights)
    assert weights == sorted(weights, reverse=True)


def test_mastery_score_formula_is_clamped():
    assert math.isclose(compute_next_mastery_score(0.0, "incorrect"), 0.0)
    assert math.isclose(compute_next_mastery_score(0.9, "correct"), 1.0)
    assert math.isclose(compute_next_mastery_score(0.2, "partial"), 0.25)
    assert math.isclose(compute_next_mastery_score(0.1, "incorrect"), 0.0)


def test_qdrant_payload_mapping_contains_expected_fields():
    captured = {}

    class FakePointStruct:
        def __init__(self, id, vector, payload):
            self.id = id
            self.vector = vector
            self.payload = payload

    class FakeModels:
        PointStruct = FakePointStruct

        class Distance:
            COSINE = "cosine"

        class VectorParams:
            def __init__(self, size, distance):
                self.size = size
                self.distance = distance

    class FakeClient:
        def get_collection(self, _name):
            raise RuntimeError("not found")

        def recreate_collection(self, collection_name, vectors_config):
            captured["collection_name"] = collection_name
            captured["vector_size"] = vectors_config.size

        def upsert(self, collection_name, points, wait=True):
            captured["upsert_collection"] = collection_name
            captured["points"] = points
            captured["wait"] = wait

    class TestEmbeddingService(EmbeddingService):
        def __init__(self):
            super().__init__()
            self.qdrant_url = "http://localhost:6333"
            self.collection_name = "content_chunks_v1"

        def _embed_texts(self, texts):
            return [[0.1, 0.2, 0.3] for _ in texts]

        def _get_qdrant_client(self):
            return FakeClient(), FakeModels

    service = TestEmbeddingService()
    ok = service.index_chunks(
        content_id="content-1",
        chunks=[
            {
                "chunk_id": "chunk-1",
                "segment_id": "seg-1",
                "segment_index": 0,
                "chunk_index": 0,
                "text": "hello vector world",
                "start_ms": 1000,
                "end_ms": 3000,
                "section_path": "intro",
                "source_type": "blog",
                "concept_ids": ["c1"],
            }
        ],
        language="en",
        user_id="user-1",
    )
    assert ok is True
    assert captured["collection_name"] == "content_chunks_v1"
    assert captured["vector_size"] == 3
    assert captured["upsert_collection"] == "content_chunks_v1"
    point = captured["points"][0]
    assert point.payload["content_id"] == "content-1"
    assert point.payload["user_id"] == "user-1"
    assert point.payload["segment_id"] == "seg-1"
    assert point.payload["concept_ids"] == ["c1"]


def test_url_validation_rejects_local_and_private_hosts():
    with pytest.raises(ValueError):
        validate_safe_http_url("http://localhost:8080/resource")
    with pytest.raises(ValueError):
        validate_safe_http_url("http://10.0.0.5/resource")


# ---------------------------------------------------------------------------
# Vector DB (Qdrant) – EmbeddingService tests
# ---------------------------------------------------------------------------

def _make_fake_qdrant(stored_points=None):
    """Build fake Qdrant client + models that capture calls and support search."""
    captured = {}
    if stored_points is None:
        stored_points = []

    class FakePointStruct:
        def __init__(self, id, vector, payload):
            self.id = id
            self.vector = vector
            self.payload = payload

    class FakeHit:
        def __init__(self, score, payload):
            self.score = score
            self.payload = payload

    class FakeModels:
        PointStruct = FakePointStruct

        class Distance:
            COSINE = "cosine"

        class VectorParams:
            def __init__(self, size, distance):
                self.size = size
                self.distance = distance

        class Filter:
            def __init__(self, must=None):
                self.must = must or []

        class FieldCondition:
            def __init__(self, key, match):
                self.key = key
                self.match = match

        class MatchValue:
            def __init__(self, value):
                self.value = value

    class FakeClient:
        def get_collection(self, _name):
            if captured.get("collection_exists"):
                return True
            raise RuntimeError("not found")

        def recreate_collection(self, collection_name, vectors_config):
            captured["recreate_called"] = True
            captured["collection_exists"] = True

        def upsert(self, collection_name, points, wait=True):
            captured["upserted"] = points
            stored_points.extend(points)

        def search(self, collection_name, query_vector, limit, query_filter=None):
            filter_values = {}
            if query_filter and query_filter.must:
                for condition in query_filter.must:
                    key = getattr(condition, "key", None)
                    match = getattr(condition, "match", None)
                    value = getattr(match, "value", None)
                    if key is not None:
                        filter_values[str(key)] = value
            hits = []
            for pt in stored_points:
                content_id_filter = filter_values.get("content_id")
                if content_id_filter and pt.payload.get("content_id") != content_id_filter:
                    continue
                user_id_filter = filter_values.get("user_id")
                if user_id_filter and pt.payload.get("user_id") != user_id_filter:
                    continue
                dot = sum(a * b for a, b in zip(query_vector, pt.vector))
                hits.append(FakeHit(score=dot, payload=pt.payload))
            hits.sort(key=lambda h: h.score, reverse=True)
            return hits[:limit]

    return FakeClient, FakeModels, captured


def _make_test_service(fake_client, fake_models):
    """Build an EmbeddingService wired to the fakes."""
    service = EmbeddingService()
    service.qdrant_url = "http://fake:6333"
    service.collection_name = "test_collection"
    service._embed_texts = lambda texts: [[float(ord(c)) for c in t[:3].ljust(3)] for t in texts]
    service._get_qdrant_client = lambda: (fake_client(), fake_models)
    return service


def test_search_chunks_returns_scored_hits():
    stored = []
    FakeClient, FakeModels, _ = _make_fake_qdrant(stored)
    service = _make_test_service(FakeClient, FakeModels)

    service.index_chunks(
        content_id="c1",
        chunks=[
            {"chunk_id": "k1", "segment_id": "s1", "segment_index": 0,
             "chunk_index": 0, "text": "abc", "start_ms": 0, "end_ms": 1000},
            {"chunk_id": "k2", "segment_id": "s2", "segment_index": 1,
             "chunk_index": 0, "text": "xyz", "start_ms": 1000, "end_ms": 2000},
        ],
        user_id="u1",
    )
    assert len(stored) == 2

    results = service.search_chunks(content_id="c1", query="abc", limit=5, user_id="u1")
    assert len(results) >= 1
    assert results[0]["payload"]["content_id"] == "c1"
    assert results[0]["payload"]["user_id"] == "u1"
    assert "score" in results[0]


def test_search_chunks_filters_by_content_id_and_user_id():
    stored = []
    FakeClient, FakeModels, _ = _make_fake_qdrant(stored)
    service = _make_test_service(FakeClient, FakeModels)

    service.index_chunks(content_id="c1", user_id="u1", chunks=[
        {"chunk_id": "k1", "text": "aaa", "segment_id": "s1"},
    ])
    service.index_chunks(content_id="c1", user_id="u2", chunks=[
        {"chunk_id": "k2", "text": "aaa", "segment_id": "s2"},
    ])
    service.index_chunks(content_id="c2", user_id="u1", chunks=[
        {"chunk_id": "k2", "text": "bbb", "segment_id": "s2"},
    ])

    results = service.search_chunks(content_id="c1", query="aaa", limit=10, user_id="u1")
    assert all(r["payload"]["content_id"] == "c1" for r in results)
    assert all(r["payload"]["user_id"] == "u1" for r in results)


def test_index_chunks_skips_when_not_configured():
    service = EmbeddingService()
    service.qdrant_url = ""
    result = service.index_chunks(content_id="c1", chunks=[{"chunk_id": "k1", "text": "hello"}])
    assert result is False


def test_search_chunks_returns_empty_when_not_configured():
    service = EmbeddingService()
    service.qdrant_url = ""
    result = service.search_chunks(content_id="c1", query="hello", user_id="u1")
    assert result == []


def test_search_chunks_returns_empty_for_blank_query():
    service = EmbeddingService()
    service.qdrant_url = "http://fake:6333"
    assert service.search_chunks(content_id="c1", query="", user_id="u1") == []
    assert service.search_chunks(content_id="c1", query="   ", user_id="u1") == []


def test_index_chunks_skips_empty_text_chunks():
    stored = []
    FakeClient, FakeModels, _ = _make_fake_qdrant(stored)
    service = _make_test_service(FakeClient, FakeModels)

    result = service.index_chunks(content_id="c1", chunks=[
        {"chunk_id": "k1", "text": ""},
        {"chunk_id": "k2", "text": "   "},
        {"chunk_id": "k3", "text": None},
    ])
    assert result is False
    assert len(stored) == 0


def test_ensure_collection_reuses_existing():
    stored = []
    FakeClient, FakeModels, captured = _make_fake_qdrant(stored)
    service = _make_test_service(FakeClient, FakeModels)

    service.index_chunks(content_id="c1", chunks=[{"chunk_id": "k1", "text": "first"}])
    assert captured.get("recreate_called") is True

    captured.pop("recreate_called", None)
    service.index_chunks(content_id="c1", chunks=[{"chunk_id": "k2", "text": "second"}])
    assert captured.get("recreate_called") is None


def test_deterministic_vector_fallback_is_stable():
    from services.learning_pipeline.embedding_service import _deterministic_vector
    v1 = _deterministic_vector("hello world")
    v2 = _deterministic_vector("hello world")
    assert v1 == v2
    assert len(v1) == 256
    assert all(isinstance(x, float) for x in v1)
    v3 = _deterministic_vector("different text")
    assert v3 != v1


def test_index_then_search_round_trip():
    """Full index→search round trip with fakes: indexed content is retrievable."""
    stored = []
    FakeClient, FakeModels, _ = _make_fake_qdrant(stored)
    service = _make_test_service(FakeClient, FakeModels)

    chunks = [
        {"chunk_id": "k1", "segment_id": "s1", "segment_index": 0,
         "chunk_index": 0, "text": "abc", "start_ms": 0, "end_ms": 5000,
         "section_path": "intro", "source_type": "blog", "concept_ids": ["c1", "c2"]},
    ]
    assert service.index_chunks(content_id="doc-42", chunks=chunks, language="en", user_id="user-42") is True

    hits = service.search_chunks(content_id="doc-42", query="abc", limit=3, user_id="user-42")
    assert len(hits) == 1
    payload = hits[0]["payload"]
    assert payload["content_id"] == "doc-42"
    assert payload["user_id"] == "user-42"
    assert payload["segment_id"] == "s1"
    assert payload["text"] == "abc"
    assert payload["concept_ids"] == ["c1", "c2"]
    assert payload["language"] == "en"
