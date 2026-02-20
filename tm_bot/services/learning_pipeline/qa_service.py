"""
Grounded Q&A service over indexed content chunks.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from services.learning_pipeline.embedding_service import EmbeddingService, VectorStoreUnavailableError
from services.learning_pipeline.learning_repo import LearningPipelineRepository
from services.learning_pipeline.llm_gateway import LearningLLMGateway
from utils.logger import get_logger

logger = get_logger(__name__)


class QAService:
    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        learning_repo: LearningPipelineRepository | None = None,
    ) -> None:
        self.embedding_service = embedding_service or EmbeddingService()
        self.learning_repo = learning_repo or LearningPipelineRepository()
        self.llm = LearningLLMGateway()

    def answer_question(self, content_id: str, user_id: str, question: str, limit: int = 8) -> Tuple[Dict[str, Any], bool]:
        question = (question or "").strip()
        if not question:
            return {"answer": "", "citations": [], "confidence": 0.0, "model_name": "none"}, False
        try:
            hits = self.embedding_service.search_chunks(
                content_id=content_id,
                query=question,
                limit=limit,
                user_id=str(user_id),
            )
        except VectorStoreUnavailableError:
            raise
        if not hits:
            hits = self._fallback_retrieval(content_id, question, limit=limit)

        citations = []
        context_blocks = []
        for idx, hit in enumerate(hits):
            payload = dict(hit.get("payload") or {})
            text_excerpt = str(payload.get("text") or "").strip()
            if not text_excerpt:
                continue
            citations.append(
                {
                    "segment_id": payload.get("segment_id"),
                    "start_ms": payload.get("start_ms"),
                    "end_ms": payload.get("end_ms"),
                    "text_excerpt": text_excerpt[:280],
                }
            )
            context_blocks.append(f"[{idx + 1}] {text_excerpt[:1000]}")
        context_text = "\n\n".join(context_blocks).strip()

        answer_text = ""
        model_name = "heuristic"
        used_fallback = False
        if context_text and self.llm.available():
            try:
                prompt = (
                    "Answer the user question using only the provided context.\n"
                    "If context is insufficient, say so briefly.\n\n"
                    f"Question: {question}\n\n"
                    f"Context:\n{context_text}\n\n"
                    "Return concise plain text."
                )
                answer_text, model_name, used_fallback = self.llm.invoke(prompt)
            except Exception as exc:
                logger.warning("LLM QA failed: %s", exc)
        if not answer_text:
            answer_text = _heuristic_answer(question, citations)

        confidence = _compute_confidence(hits, citations)
        return {
            "answer": answer_text,
            "citations": citations,
            "confidence": confidence,
            "model_name": model_name,
        }, used_fallback

    def _fallback_retrieval(self, content_id: str, question: str, limit: int = 8) -> List[Dict[str, Any]]:
        terms = set(re.findall(r"[a-zA-Z0-9_]{2,}", question.lower()))
        segments = self.learning_repo.list_segments(content_id)
        scored = []
        for segment in segments:
            text = str(segment.get("text") or "")
            words = set(re.findall(r"[a-zA-Z0-9_]{2,}", text.lower()))
            overlap = len(terms.intersection(words))
            if overlap <= 0:
                continue
            scored.append(
                {
                    "score": float(overlap),
                    "payload": {
                        "segment_id": segment.get("id"),
                        "start_ms": segment.get("start_ms"),
                        "end_ms": segment.get("end_ms"),
                        "text": text,
                    },
                }
            )
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[: max(1, int(limit))]


def _heuristic_answer(question: str, citations: List[Dict[str, Any]]) -> str:
    if not citations:
        return "I could not find enough grounded context to answer this question yet."
    top = citations[0].get("text_excerpt") or ""
    if not top:
        return "I found context, but it is too sparse to answer confidently."
    return f"Based on the content, the most relevant point is: {top}"


def _compute_confidence(hits: List[Dict[str, Any]], citations: List[Dict[str, Any]]) -> float:
    if not hits or not citations:
        return 0.2
    top_score = float(hits[0].get("score") or 0.0)
    if top_score <= 0:
        return 0.35
    score = min(0.95, 0.45 + min(0.4, top_score / 10.0))
    return round(score, 3)
