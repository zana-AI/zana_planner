"""
Async worker for processing content learning jobs.
"""

from __future__ import annotations

import asyncio
import os
import socket
import traceback
import uuid
from typing import Any, Dict, Optional

from repositories.content_repo import ContentRepository
from services.learning_pipeline.analysis_service import AnalysisService
from services.learning_pipeline.constants import MAX_RETRIES, RETRY_BACKOFF_SECONDS
from services.learning_pipeline.embedding_service import EmbeddingService
from services.learning_pipeline.ingestors import BlogIngestor, PodcastIngestor, YouTubeIngestor
from services.learning_pipeline.job_repo import LearningPipelineJobRepository
from services.learning_pipeline.learning_repo import LearningPipelineRepository
from services.learning_pipeline.quiz_service import QuizService
from services.learning_pipeline.security import validate_safe_http_url
from services.learning_pipeline.segmenter import Segmenter
from services.learning_pipeline.transcription_service import TranscriptionService
from services.learning_pipeline.types import SegmentRecord
from utils.logger import get_logger

logger = get_logger(__name__)


class LearningPipelineWorker:
    def __init__(self) -> None:
        self.enabled = os.getenv("CONTENT_LEARNING_PIPELINE_ENABLED", "false").strip().lower() in ("1", "true", "yes")
        self.poll_interval_seconds = 5
        self.worker_id = f"{socket.gethostname()}-{uuid.uuid4()}"
        self._stop_event = asyncio.Event()
        self._dispatcher_task: Optional[asyncio.Task] = None
        self._running_tasks: set[asyncio.Task] = set()
        self._max_concurrent_jobs = 4
        self._ingest_semaphore = asyncio.Semaphore(2)
        self._analysis_semaphore = asyncio.Semaphore(2)

        self.job_repo = LearningPipelineJobRepository()
        self.learning_repo = LearningPipelineRepository()
        self.content_repo = ContentRepository()
        self.youtube_ingestor = YouTubeIngestor()
        self.blog_ingestor = BlogIngestor()
        self.podcast_ingestor = PodcastIngestor()
        self.transcription_service = TranscriptionService()
        self.segmenter = Segmenter(chunk_size=1200, chunk_overlap=180)
        self.embedding_service = EmbeddingService()
        self.analysis_service = AnalysisService()
        self.quiz_service = QuizService(self.learning_repo)

    async def start(self) -> None:
        if not self.enabled:
            logger.info("Learning pipeline worker is disabled (CONTENT_LEARNING_PIPELINE_ENABLED=false)")
            return
        if self._dispatcher_task and not self._dispatcher_task.done():
            return
        self._stop_event.clear()
        self._dispatcher_task = asyncio.create_task(self._dispatch_loop(), name="learning-pipeline-dispatcher")
        logger.info("Learning pipeline worker started with worker_id=%s", self.worker_id)

    async def stop(self) -> None:
        if not self.enabled:
            return
        self._stop_event.set()
        if self._dispatcher_task:
            self._dispatcher_task.cancel()
            try:
                await self._dispatcher_task
            except asyncio.CancelledError:
                pass
        if self._running_tasks:
            for task in list(self._running_tasks):
                task.cancel()
            await asyncio.gather(*self._running_tasks, return_exceptions=True)
        released = self.job_repo.release_worker_jobs(self.worker_id)
        logger.info("Learning pipeline worker stopped; released_jobs=%s", released)

    async def _dispatch_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._dispatch_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Learning pipeline dispatcher error: %s", exc, exc_info=True)
            await asyncio.sleep(self.poll_interval_seconds)

    async def _dispatch_once(self) -> None:
        while len(self._running_tasks) < self._max_concurrent_jobs:
            job = self.job_repo.claim_next_pending(self.worker_id)
            if not job:
                break
            task = asyncio.create_task(self._process_job(job), name=f"learning-job-{job['id']}")
            self._running_tasks.add(task)
            task.add_done_callback(self._running_tasks.discard)

    async def _process_job(self, job: Dict[str, Any]) -> None:
        job_id = str(job.get("id"))
        content_id = str(job.get("content_id"))
        user_id = str(job.get("user_id"))
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self.job_repo.set_attempt_count(job_id, attempt)
                self.job_repo.mark_running(job_id)
                await self._run_pipeline(job_id=job_id, content_id=content_id, user_id=user_id)
                self.job_repo.mark_completed(job_id)
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                err_text = f"{exc}"
                logger.error(
                    "Learning pipeline job failed (job_id=%s, attempt=%s/%s): %s",
                    job_id,
                    attempt,
                    MAX_RETRIES,
                    err_text,
                )
                self.job_repo.mark_error(job_id, "pipeline_error", f"{err_text}\n{traceback.format_exc()}"[:2000])
                if attempt >= MAX_RETRIES:
                    self.job_repo.mark_failed(job_id, "pipeline_failed", err_text)
                    return
                await asyncio.sleep(RETRY_BACKOFF_SECONDS[min(attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)])

    async def _run_pipeline(self, job_id: str, content_id: str, user_id: str) -> None:
        self.job_repo.set_stage(job_id, "resolve")
        content = self.content_repo.get_content_by_id(content_id)
        if not content:
            raise ValueError("Content not found")
        source_url = str(content.get("original_url") or content.get("canonical_url") or "").strip()
        if not source_url:
            raise ValueError("Content URL is missing")
        validate_safe_http_url(source_url)

        self.job_repo.set_stage(job_id, "fetch")
        async with self._ingest_semaphore:
            ingested = await asyncio.to_thread(self._ingest_content, content)
        for asset in ingested.assets:
            self.learning_repo.add_asset(
                content_id=content_id,
                asset_type=asset.get("asset_type") or "metadata_json",
                storage_uri=asset.get("storage_uri") or "inline://unknown",
                size_bytes=asset.get("size_bytes"),
                checksum=asset.get("checksum"),
            )

        segments = list(ingested.segments or [])
        if ingested.needs_transcription:
            self.job_repo.set_stage(job_id, "transcribe")
            async with self._ingest_semaphore:
                try:
                    transcribed = await asyncio.to_thread(
                        self.transcription_service.transcribe_audio_url,
                        ingested.audio_url or source_url,
                        "en-US",
                        content.get("duration_seconds"),
                    )
                except Exception as exc:
                    logger.warning("Transcription failed for content_id=%s: %s", content_id, exc)
                    transcribed = []
            if transcribed:
                segments = transcribed

        if not segments and ingested.text:
            self.job_repo.set_stage(job_id, "segment")
            segments = self.segmenter.segment_text(ingested.text, section_path="content")
        elif segments:
            self.job_repo.set_stage(job_id, "segment")

        if not segments:
            raise ValueError("No content segments available after ingestion/transcription")

        inserted_segments = self.learning_repo.replace_segments(content_id, segments)

        self.job_repo.set_stage(job_id, "embed")
        chunks = self.segmenter.build_chunks(inserted_segments)
        for chunk in chunks:
            chunk["source_type"] = ingested.source_type
        async with self._analysis_semaphore:
            await asyncio.to_thread(
                self.embedding_service.index_chunks,
                content_id,
                chunks,
                ingested.language,
                user_id,
            )

        self.job_repo.set_stage(job_id, "summarize")
        async with self._analysis_semaphore:
            summaries, summary_fallback_used, summary_model = await asyncio.to_thread(
                self.analysis_service.generate_summaries,
                inserted_segments,
            )
        for artifact_type, payload in summaries.items():
            self.learning_repo.add_artifact(
                content_id=content_id,
                artifact_type=artifact_type,
                artifact_format="json",
                payload_json=payload,
                model_name=summary_model,
            )
        if summary_fallback_used:
            self.job_repo.mark_gemini_fallback_used(job_id)

        self.job_repo.set_stage(job_id, "concept_extract")
        async with self._analysis_semaphore:
            concept_payload, concept_fallback_used, concept_model = await asyncio.to_thread(
                self.analysis_service.extract_concepts,
                inserted_segments,
            )
        concepts = concept_payload.get("concepts") or []
        edges = concept_payload.get("edges") or []
        self.learning_repo.replace_concepts_and_edges(content_id=content_id, concepts=concepts, edges=edges)
        self.learning_repo.add_artifact(
            content_id=content_id,
            artifact_type="qa_seed",
            artifact_format="json",
            payload_json={"concept_count": len(concepts), "edge_count": len(edges)},
            model_name=concept_model,
        )
        if concept_fallback_used:
            self.job_repo.mark_gemini_fallback_used(job_id)

        self.job_repo.set_stage(job_id, "quiz_generate")
        async with self._analysis_semaphore:
            quiz_payload, quiz_fallback_used = await asyncio.to_thread(
                self.quiz_service.create_quiz,
                content_id,
                "medium",
                8,
            )
        self.learning_repo.add_artifact(
            content_id=content_id,
            artifact_type="quiz_seed",
            artifact_format="json",
            payload_json=quiz_payload,
            model_name="heuristic_or_llm",
        )
        if quiz_fallback_used:
            self.job_repo.mark_gemini_fallback_used(job_id)
        self.job_repo.set_stage(job_id, "done")

    def _ingest_content(self, content: Dict[str, Any]):
        provider = str(content.get("provider") or "").lower()
        content_type = str(content.get("content_type") or "").lower()
        source_url = str(content.get("original_url") or content.get("canonical_url") or "").strip()
        if provider == "youtube" or content_type == "video":
            return self.youtube_ingestor.ingest(source_url, content)
        if provider in ("podcast",) or content_type == "audio":
            return self.podcast_ingestor.ingest(source_url, content)
        return self.blog_ingestor.ingest(source_url, content)
