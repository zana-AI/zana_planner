"""
Facade service for API handlers.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from repositories.content_repo import ContentRepository
from services.learning_pipeline.job_repo import LearningPipelineJobRepository
from services.learning_pipeline.learning_repo import LearningPipelineRepository
from services.learning_pipeline.qa_service import QAService
from services.learning_pipeline.quiz_service import QuizService
from utils.logger import get_logger

logger = get_logger(__name__)


class LearningPipelineService:
    def __init__(self) -> None:
        self.enabled = os.getenv("CONTENT_LEARNING_PIPELINE_ENABLED", "false").strip().lower() in ("1", "true", "yes")
        self.content_repo = ContentRepository()
        self.job_repo = LearningPipelineJobRepository()
        self.learning_repo = LearningPipelineRepository()
        self.qa_service = QAService(learning_repo=self.learning_repo)
        self.quiz_service = QuizService(learning_repo=self.learning_repo)

    def enqueue_analysis(self, user_id: int, content_id: str, force_rebuild: bool = False) -> Dict[str, Any]:
        self._ensure_enabled()
        content_id = str(content_id)
        content = self.content_repo.get_content_by_id(content_id)
        if not content:
            raise ValueError("Content not found")
        self._assert_user_has_content(user_id=user_id, content_id=content_id)
        if force_rebuild:
            self.learning_repo.clear_content_learning_data(content_id)
        job = self.job_repo.create_or_reuse_job(
            user_id=str(user_id),
            content_id=content_id,
            force_rebuild=force_rebuild,
        )
        return {"job_id": job["id"], "status": job["status"], "stage": job["stage"], "progress_pct": job["progress_pct"]}

    def get_job_status(self, job_id: str, user_id: int) -> Dict[str, Any]:
        self._ensure_enabled()
        job = self.job_repo.get_job(job_id)
        if not job:
            raise ValueError("Job not found")
        self._assert_user_has_content(user_id=user_id, content_id=str(job.get("content_id") or ""))
        return {
            "job_id": job["id"],
            "status": job["status"],
            "stage": job["stage"],
            "progress_pct": job["progress_pct"],
            "error_code": job.get("error_code"),
            "error_detail": job.get("error_detail"),
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
        }

    def get_summary(self, content_id: str, user_id: int, level: str = "global") -> Dict[str, Any]:
        self._ensure_enabled()
        content_id = str(content_id)
        self._assert_user_has_content(user_id=user_id, content_id=content_id)
        level = (level or "global").strip().lower()
        if level not in ("global", "section"):
            raise ValueError("level must be 'global' or 'section'")
        artifact_type = "summary_global" if level == "global" else "summary_section"
        artifact = self.learning_repo.get_latest_artifact(content_id, artifact_type)
        if not artifact:
            raise ValueError("Summary not found. Run analyze first.")
        payload = artifact.get("payload_json") or {}
        return {"level": level, "summary": payload, "model_name": artifact.get("model_name"), "created_at": artifact.get("created_at")}

    def ask(self, content_id: str, user_id: int, question: str) -> Dict[str, Any]:
        self._ensure_enabled()
        content_id = str(content_id)
        self._assert_user_has_content(user_id=user_id, content_id=content_id)
        response, used_fallback = self.qa_service.answer_question(
            content_id=content_id,
            user_id=str(user_id),
            question=question,
            limit=8,
        )
        response["used_fallback"] = used_fallback
        return response

    def create_quiz(
        self,
        content_id: str,
        user_id: int,
        difficulty: str = "medium",
        question_count: int = 8,
    ) -> Dict[str, Any]:
        self._ensure_enabled()
        content_id = str(content_id)
        self._assert_user_has_content(user_id=user_id, content_id=content_id)
        payload, used_fallback = self.quiz_service.create_quiz(
            content_id=content_id,
            difficulty=difficulty,
            question_count=question_count,
        )
        payload["used_fallback"] = used_fallback
        return payload

    def submit_quiz(
        self,
        user_id: int,
        quiz_set_id: str,
        answers: List[Dict[str, Any]],
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._ensure_enabled()
        quiz_set = self.learning_repo.get_quiz_set(quiz_set_id)
        if not quiz_set:
            raise ValueError("Quiz not found")
        self._assert_user_has_content(user_id=user_id, content_id=str(quiz_set.get("content_id") or ""))
        payload, used_fallback = self.quiz_service.submit_answers(
            user_id=str(user_id),
            quiz_set_id=quiz_set_id,
            answers=answers,
            idempotency_key=idempotency_key,
        )
        payload["used_fallback"] = used_fallback
        return payload

    def get_concepts(self, content_id: str, user_id: int) -> Dict[str, Any]:
        self._ensure_enabled()
        content_id = str(content_id)
        self._assert_user_has_content(user_id=user_id, content_id=content_id)
        graph = self.learning_repo.get_concepts_graph(content_id)
        return graph

    def _ensure_enabled(self) -> None:
        if not self.enabled:
            raise RuntimeError("Content learning pipeline is disabled")

    def _assert_user_has_content(self, user_id: int, content_id: str) -> None:
        if not content_id:
            raise ValueError("Content not found")
        user_content = self.content_repo.get_user_content(str(user_id), str(content_id))
        if not user_content:
            raise ValueError("User content not found")
