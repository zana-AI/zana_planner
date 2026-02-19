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
    )
    assert ok is True
    assert captured["collection_name"] == "content_chunks_v1"
    assert captured["vector_size"] == 3
    assert captured["upsert_collection"] == "content_chunks_v1"
    point = captured["points"][0]
    assert point.payload["content_id"] == "content-1"
    assert point.payload["segment_id"] == "seg-1"
    assert point.payload["concept_ids"] == ["c1"]


def test_url_validation_rejects_local_and_private_hosts():
    with pytest.raises(ValueError):
        validate_safe_http_url("http://localhost:8080/resource")
    with pytest.raises(ValueError):
        validate_safe_http_url("http://10.0.0.5/resource")
