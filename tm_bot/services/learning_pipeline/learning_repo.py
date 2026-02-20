"""
Repository for learning pipeline artifacts, concepts, quizzes, and mastery.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import bindparam, text
from sqlalchemy.exc import IntegrityError

from db.postgres_db import get_db_session, utc_now_iso
from services.learning_pipeline.types import SegmentRecord


class LearningPipelineRepository:
    def clear_content_learning_data(self, content_id: str) -> None:
        content_id = str(content_id)
        with get_db_session() as session:
            concept_ids = session.execute(
                text("SELECT id FROM content_concept WHERE content_id = :content_id"),
                {"content_id": content_id},
            ).fetchall()
            concept_id_values = [str(row[0]) for row in concept_ids]

            session.execute(
                text(
                    """
                    DELETE FROM quiz_attempt_answer
                    WHERE attempt_id IN (
                        SELECT qa.id
                        FROM quiz_attempt qa
                        JOIN quiz_set qs ON qs.id = qa.quiz_set_id
                        WHERE qs.content_id = :content_id
                    )
                    """
                ),
                {"content_id": content_id},
            )
            session.execute(
                text(
                    """
                    DELETE FROM quiz_attempt
                    WHERE quiz_set_id IN (SELECT id FROM quiz_set WHERE content_id = :content_id)
                    """
                ),
                {"content_id": content_id},
            )
            session.execute(
                text(
                    """
                    DELETE FROM quiz_question
                    WHERE quiz_set_id IN (SELECT id FROM quiz_set WHERE content_id = :content_id)
                    """
                ),
                {"content_id": content_id},
            )
            session.execute(
                text("DELETE FROM quiz_set WHERE content_id = :content_id"),
                {"content_id": content_id},
            )
            if concept_id_values:
                delete_mastery_stmt = text(
                    """
                    DELETE FROM user_concept_mastery
                    WHERE concept_id IN :concept_ids
                    """
                ).bindparams(bindparam("concept_ids", expanding=True))
                session.execute(
                    delete_mastery_stmt,
                    {"concept_ids": concept_id_values},
                )
            session.execute(
                text("DELETE FROM content_concept_edge WHERE content_id = :content_id"),
                {"content_id": content_id},
            )
            session.execute(
                text("DELETE FROM content_concept WHERE content_id = :content_id"),
                {"content_id": content_id},
            )
            session.execute(
                text("DELETE FROM content_artifact WHERE content_id = :content_id"),
                {"content_id": content_id},
            )
            session.execute(
                text("DELETE FROM content_segment WHERE content_id = :content_id"),
                {"content_id": content_id},
            )
            session.execute(
                text("DELETE FROM content_asset WHERE content_id = :content_id"),
                {"content_id": content_id},
            )

    def add_asset(
        self,
        content_id: str,
        asset_type: str,
        storage_uri: str,
        size_bytes: Optional[int] = None,
        checksum: Optional[str] = None,
    ) -> str:
        asset_id = str(uuid.uuid4())
        now = utc_now_iso()
        with get_db_session() as session:
            session.execute(
                text(
                    """
                    INSERT INTO content_asset (id, content_id, asset_type, storage_uri, size_bytes, checksum, created_at)
                    VALUES (:id, :content_id, :asset_type, :storage_uri, :size_bytes, :checksum, :created_at)
                    """
                ),
                {
                    "id": asset_id,
                    "content_id": str(content_id),
                    "asset_type": str(asset_type),
                    "storage_uri": str(storage_uri),
                    "size_bytes": size_bytes,
                    "checksum": checksum,
                    "created_at": now,
                },
            )
        return asset_id

    def replace_segments(self, content_id: str, segments: Iterable[SegmentRecord]) -> List[Dict[str, Any]]:
        content_id = str(content_id)
        now = utc_now_iso()
        inserted: List[Dict[str, Any]] = []
        with get_db_session() as session:
            session.execute(text("DELETE FROM content_segment WHERE content_id = :content_id"), {"content_id": content_id})
            for idx, segment in enumerate(segments):
                segment_id = str(uuid.uuid4())
                token_count = segment.token_count
                if token_count is None:
                    token_count = _estimate_token_count(segment.text)
                session.execute(
                    text(
                        """
                        INSERT INTO content_segment (
                            id, content_id, segment_index, text, start_ms, end_ms, section_path, token_count, created_at
                        ) VALUES (
                            :id, :content_id, :segment_index, :text, :start_ms, :end_ms, :section_path, :token_count, :created_at
                        )
                        """
                    ),
                    {
                        "id": segment_id,
                        "content_id": content_id,
                        "segment_index": idx,
                        "text": segment.text,
                        "start_ms": segment.start_ms,
                        "end_ms": segment.end_ms,
                        "section_path": segment.section_path,
                        "token_count": token_count,
                        "created_at": now,
                    },
                )
                inserted.append(
                    {
                        "id": segment_id,
                        "content_id": content_id,
                        "segment_index": idx,
                        "text": segment.text,
                        "start_ms": segment.start_ms,
                        "end_ms": segment.end_ms,
                        "section_path": segment.section_path,
                        "token_count": token_count,
                    }
                )
        return inserted

    def list_segments(self, content_id: str) -> List[Dict[str, Any]]:
        with get_db_session() as session:
            rows = session.execute(
                text(
                    """
                    SELECT id, content_id, segment_index, text, start_ms, end_ms, section_path, token_count, created_at
                    FROM content_segment
                    WHERE content_id = :content_id
                    ORDER BY segment_index ASC
                    """
                ),
                {"content_id": str(content_id)},
            ).mappings().fetchall()
        return [dict(row) for row in rows]

    def add_artifact(
        self,
        content_id: str,
        artifact_type: str,
        artifact_format: str,
        payload_json: Dict[str, Any],
        model_name: Optional[str] = None,
    ) -> str:
        artifact_id = str(uuid.uuid4())
        now = utc_now_iso()
        with get_db_session() as session:
            session.execute(
                text(
                    """
                    INSERT INTO content_artifact (id, content_id, artifact_type, artifact_format, payload_json, model_name, created_at)
                    VALUES (:id, :content_id, :artifact_type, :artifact_format, CAST(:payload_json AS jsonb), :model_name, :created_at)
                    """
                ),
                {
                    "id": artifact_id,
                    "content_id": str(content_id),
                    "artifact_type": str(artifact_type),
                    "artifact_format": str(artifact_format),
                    "payload_json": json.dumps(payload_json or {}),
                    "model_name": model_name,
                    "created_at": now,
                },
            )
        return artifact_id

    def get_latest_artifact(self, content_id: str, artifact_type: str) -> Optional[Dict[str, Any]]:
        with get_db_session() as session:
            row = session.execute(
                text(
                    """
                    SELECT id, content_id, artifact_type, artifact_format, payload_json, model_name, created_at
                    FROM content_artifact
                    WHERE content_id = :content_id
                      AND artifact_type = :artifact_type
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {"content_id": str(content_id), "artifact_type": str(artifact_type)},
            ).mappings().fetchone()
        if not row:
            return None
        result = dict(row)
        if not isinstance(result.get("payload_json"), dict):
            result["payload_json"] = _json_loads_safe(result.get("payload_json"), {})
        return result

    def replace_concepts_and_edges(
        self,
        content_id: str,
        concepts: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
    ) -> Dict[str, str]:
        content_id = str(content_id)
        now = utc_now_iso()
        concept_id_by_label: Dict[str, str] = {}
        with get_db_session() as session:
            session.execute(text("DELETE FROM content_concept_edge WHERE content_id = :content_id"), {"content_id": content_id})
            session.execute(text("DELETE FROM content_concept WHERE content_id = :content_id"), {"content_id": content_id})
            for concept in concepts:
                label = str(concept.get("label") or "").strip()
                if not label:
                    continue
                concept_id = str(uuid.uuid4())
                concept_id_by_label[label.lower()] = concept_id
                session.execute(
                    text(
                        """
                        INSERT INTO content_concept (
                            id, content_id, label, concept_type, definition, examples_json,
                            importance_weight, support_count, created_at, updated_at
                        ) VALUES (
                            :id, :content_id, :label, :concept_type, :definition, CAST(:examples_json AS jsonb),
                            :importance_weight, :support_count, :created_at, :updated_at
                        )
                        """
                    ),
                    {
                        "id": concept_id,
                        "content_id": content_id,
                        "label": label,
                        "concept_type": concept.get("concept_type"),
                        "definition": concept.get("definition"),
                        "examples_json": json.dumps(concept.get("examples") or []),
                        "importance_weight": float(concept.get("importance_weight") or 0.0),
                        "support_count": int(concept.get("support_count") or 0),
                        "created_at": now,
                        "updated_at": now,
                    },
                )

            for edge in edges:
                source_raw = str(edge.get("source") or "").strip().lower()
                target_raw = str(edge.get("target") or "").strip().lower()
                source_id = concept_id_by_label.get(source_raw)
                target_id = concept_id_by_label.get(target_raw)
                if not source_id or not target_id or source_id == target_id:
                    continue
                session.execute(
                    text(
                        """
                        INSERT INTO content_concept_edge (
                            id, content_id, source_concept_id, target_concept_id, relation_type, confidence, weight, created_at
                        ) VALUES (
                            :id, :content_id, :source_concept_id, :target_concept_id, :relation_type, :confidence, :weight, :created_at
                        )
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "content_id": content_id,
                        "source_concept_id": source_id,
                        "target_concept_id": target_id,
                        "relation_type": str(edge.get("relation_type") or "related_to"),
                        "confidence": float(edge.get("confidence") or 0.0),
                        "weight": float(edge.get("weight") or 0.0),
                        "created_at": now,
                    },
                )
        return concept_id_by_label

    def get_concepts_graph(self, content_id: str) -> Dict[str, Any]:
        with get_db_session() as session:
            nodes = session.execute(
                text(
                    """
                    SELECT id, content_id, label, concept_type, definition, examples_json, importance_weight, support_count
                    FROM content_concept
                    WHERE content_id = :content_id
                    ORDER BY importance_weight DESC, label ASC
                    """
                ),
                {"content_id": str(content_id)},
            ).mappings().fetchall()
            edges = session.execute(
                text(
                    """
                    SELECT id, content_id, source_concept_id, target_concept_id, relation_type, confidence, weight
                    FROM content_concept_edge
                    WHERE content_id = :content_id
                    """
                ),
                {"content_id": str(content_id)},
            ).mappings().fetchall()
        node_items = []
        for node in nodes:
            item = dict(node)
            if not isinstance(item.get("examples_json"), list):
                item["examples_json"] = _json_loads_safe(item.get("examples_json"), [])
            node_items.append(item)
        return {"nodes": node_items, "edges": [dict(edge) for edge in edges]}

    def create_quiz_set(
        self,
        content_id: str,
        title: str,
        difficulty: str,
        questions: List[Dict[str, Any]],
        concept_id_by_label: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        content_id = str(content_id)
        now = utc_now_iso()
        concept_map = {k.lower(): v for k, v in (concept_id_by_label or {}).items()}
        with get_db_session() as session:
            version_row = session.execute(
                text("SELECT COALESCE(MAX(version), 0) AS max_version FROM quiz_set WHERE content_id = :content_id"),
                {"content_id": content_id},
            ).mappings().fetchone()
            version = int(version_row["max_version"] or 0) + 1
            quiz_set_id = str(uuid.uuid4())
            session.execute(
                text(
                    """
                    INSERT INTO quiz_set (id, content_id, version, title, difficulty, created_at)
                    VALUES (:id, :content_id, :version, :title, :difficulty, :created_at)
                    """
                ),
                {
                    "id": quiz_set_id,
                    "content_id": content_id,
                    "version": version,
                    "title": title,
                    "difficulty": difficulty,
                    "created_at": now,
                },
            )
            created_questions = []
            for idx, question in enumerate(questions):
                question_id = str(uuid.uuid4())
                concept_id = question.get("concept_id")
                if not concept_id:
                    label = str(question.get("concept_label") or "").strip().lower()
                    concept_id = concept_map.get(label)
                session.execute(
                    text(
                        """
                        INSERT INTO quiz_question (
                            id, quiz_set_id, concept_id, question_type, difficulty, prompt,
                            options_json, answer_key_json, rationale, source_segment_ids_json, position
                        ) VALUES (
                            :id, :quiz_set_id, :concept_id, :question_type, :difficulty, :prompt,
                            CAST(:options_json AS jsonb), CAST(:answer_key_json AS jsonb), :rationale, CAST(:source_segment_ids_json AS jsonb), :position
                        )
                        """
                    ),
                    {
                        "id": question_id,
                        "quiz_set_id": quiz_set_id,
                        "concept_id": concept_id,
                        "question_type": question.get("question_type") or "mcq",
                        "difficulty": question.get("difficulty") or difficulty,
                        "prompt": question.get("prompt") or "",
                        "options_json": json.dumps(question.get("options") or []),
                        "answer_key_json": json.dumps(question.get("answer_key") or {}),
                        "rationale": question.get("rationale"),
                        "source_segment_ids_json": json.dumps(question.get("source_segment_ids") or []),
                        "position": int(question.get("position") or (idx + 1)),
                    },
                )
                created_questions.append({"id": question_id, **question})
        return {"quiz_set_id": quiz_set_id, "version": version, "questions": created_questions}

    def get_quiz_set(self, quiz_set_id: str) -> Optional[Dict[str, Any]]:
        with get_db_session() as session:
            row = session.execute(
                text(
                    """
                    SELECT id, content_id, version, title, difficulty, created_at
                    FROM quiz_set
                    WHERE id = :quiz_set_id
                    """
                ),
                {"quiz_set_id": str(quiz_set_id)},
            ).mappings().fetchone()
        return dict(row) if row else None

    def get_latest_quiz_set_for_content(self, content_id: str, difficulty: Optional[str] = None) -> Optional[Dict[str, Any]]:
        params: Dict[str, Any] = {"content_id": str(content_id)}
        query = """
            SELECT id, content_id, version, title, difficulty, created_at
            FROM quiz_set
            WHERE content_id = :content_id
        """
        if difficulty:
            query += " AND difficulty = :difficulty"
            params["difficulty"] = difficulty
        query += " ORDER BY version DESC LIMIT 1"
        with get_db_session() as session:
            row = session.execute(text(query), params).mappings().fetchone()
        return dict(row) if row else None

    def get_quiz_questions(self, quiz_set_id: str) -> List[Dict[str, Any]]:
        with get_db_session() as session:
            rows = session.execute(
                text(
                    """
                    SELECT id, quiz_set_id, concept_id, question_type, difficulty, prompt, options_json,
                           answer_key_json, rationale, source_segment_ids_json, position
                    FROM quiz_question
                    WHERE quiz_set_id = :quiz_set_id
                    ORDER BY position ASC
                    """
                ),
                {"quiz_set_id": str(quiz_set_id)},
            ).mappings().fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["options_json"] = item["options_json"] if isinstance(item.get("options_json"), list) else _json_loads_safe(item.get("options_json"), [])
            item["answer_key_json"] = item["answer_key_json"] if isinstance(item.get("answer_key_json"), dict) else _json_loads_safe(item.get("answer_key_json"), {})
            item["source_segment_ids_json"] = (
                item["source_segment_ids_json"]
                if isinstance(item.get("source_segment_ids_json"), list)
                else _json_loads_safe(item.get("source_segment_ids_json"), [])
            )
            result.append(item)
        return result

    def find_attempt_by_idempotency(
        self,
        user_id: str,
        quiz_set_id: str,
        idempotency_key: str,
    ) -> Optional[Dict[str, Any]]:
        if not idempotency_key:
            return None
        with get_db_session() as session:
            row = session.execute(
                text(
                    """
                    SELECT id, user_id, quiz_set_id, score, max_score, started_at, submitted_at, graded_at, status, idempotency_key
                    FROM quiz_attempt
                    WHERE user_id = :user_id
                      AND quiz_set_id = :quiz_set_id
                      AND idempotency_key = :idempotency_key
                    LIMIT 1
                    """
                ),
                {
                    "user_id": str(user_id),
                    "quiz_set_id": str(quiz_set_id),
                    "idempotency_key": str(idempotency_key),
                },
            ).mappings().fetchone()
        return dict(row) if row else None

    def create_attempt(self, user_id: str, quiz_set_id: str, idempotency_key: Optional[str] = None) -> str:
        attempt_id = str(uuid.uuid4())
        now = utc_now_iso()
        with get_db_session() as session:
            try:
                session.execute(
                    text(
                        """
                        INSERT INTO quiz_attempt (
                            id, user_id, quiz_set_id, score, max_score, started_at, status, idempotency_key
                        ) VALUES (
                            :id, :user_id, :quiz_set_id, 0, 0, :started_at, 'in_progress', :idempotency_key
                        )
                        """
                    ),
                    {
                        "id": attempt_id,
                        "user_id": str(user_id),
                        "quiz_set_id": str(quiz_set_id),
                        "started_at": now,
                        "idempotency_key": idempotency_key,
                    },
                )
            except IntegrityError:
                if idempotency_key:
                    existing = session.execute(
                        text(
                            """
                            SELECT id
                            FROM quiz_attempt
                            WHERE user_id = :user_id
                              AND quiz_set_id = :quiz_set_id
                              AND idempotency_key = :idempotency_key
                            LIMIT 1
                            """
                        ),
                        {
                            "user_id": str(user_id),
                            "quiz_set_id": str(quiz_set_id),
                            "idempotency_key": str(idempotency_key),
                        },
                    ).mappings().fetchone()
                    if existing:
                        return str(existing["id"])
                raise
        return attempt_id

    def finalize_attempt(
        self,
        attempt_id: str,
        score: float,
        max_score: float,
        answers: List[Dict[str, Any]],
    ) -> None:
        now = utc_now_iso()
        with get_db_session() as session:
            session.execute(
                text("DELETE FROM quiz_attempt_answer WHERE attempt_id = :attempt_id"),
                {"attempt_id": str(attempt_id)},
            )
            for answer in answers:
                session.execute(
                    text(
                        """
                        INSERT INTO quiz_attempt_answer (
                            id, attempt_id, question_id, user_answer_json, is_correct,
                            score_awarded, feedback, graded_by_model, created_at
                        ) VALUES (
                            :id, :attempt_id, :question_id, CAST(:user_answer_json AS jsonb), :is_correct,
                            :score_awarded, :feedback, :graded_by_model, :created_at
                        )
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "attempt_id": str(attempt_id),
                        "question_id": str(answer.get("question_id")),
                        "user_answer_json": json.dumps(answer.get("user_answer_json") or {}),
                        "is_correct": answer.get("is_correct"),
                        "score_awarded": float(answer.get("score_awarded") or 0.0),
                        "feedback": answer.get("feedback"),
                        "graded_by_model": answer.get("graded_by_model"),
                        "created_at": now,
                    },
                )
            session.execute(
                text(
                    """
                    UPDATE quiz_attempt
                    SET score = :score,
                        max_score = :max_score,
                        submitted_at = :submitted_at,
                        graded_at = :graded_at,
                        status = 'graded'
                    WHERE id = :attempt_id
                    """
                ),
                {
                    "attempt_id": str(attempt_id),
                    "score": float(score),
                    "max_score": float(max_score),
                    "submitted_at": now,
                    "graded_at": now,
                },
            )

    def get_attempt_report(self, attempt_id: str) -> Optional[Dict[str, Any]]:
        with get_db_session() as session:
            attempt = session.execute(
                text(
                    """
                    SELECT id, user_id, quiz_set_id, score, max_score, started_at, submitted_at, graded_at, status, idempotency_key
                    FROM quiz_attempt
                    WHERE id = :attempt_id
                    """
                ),
                {"attempt_id": str(attempt_id)},
            ).mappings().fetchone()
            if not attempt:
                return None
            answers = session.execute(
                text(
                    """
                    SELECT question_id, user_answer_json, is_correct, score_awarded, feedback, graded_by_model
                    FROM quiz_attempt_answer
                    WHERE attempt_id = :attempt_id
                    ORDER BY created_at ASC
                    """
                ),
                {"attempt_id": str(attempt_id)},
            ).mappings().fetchall()
        answer_rows = []
        for row in answers:
            item = dict(row)
            if not isinstance(item.get("user_answer_json"), dict):
                item["user_answer_json"] = _json_loads_safe(item.get("user_answer_json"), {})
            answer_rows.append(item)
        return {**dict(attempt), "answers": answer_rows}

    def apply_mastery_result(self, user_id: str, concept_id: str, result_label: str) -> Dict[str, Any]:
        user_id = str(user_id)
        concept_id = str(concept_id)
        result_label = (result_label or "incorrect").strip().lower()
        correct_increment = 1 if result_label == "correct" else 0
        now = utc_now_iso()
        with get_db_session() as session:
            existing = session.execute(
                text(
                    """
                    SELECT mastery_score, attempt_count, correct_count
                    FROM user_concept_mastery
                    WHERE user_id = :user_id AND concept_id = :concept_id
                    """
                ),
                {"user_id": user_id, "concept_id": concept_id},
            ).mappings().fetchone()
            if not existing:
                new_score = compute_next_mastery_score(0.0, result_label)
                session.execute(
                    text(
                        """
                        INSERT INTO user_concept_mastery (
                            user_id, concept_id, mastery_score, attempt_count, correct_count, last_tested_at, updated_at
                        ) VALUES (
                            :user_id, :concept_id, :mastery_score, 1, :correct_count, :last_tested_at, :updated_at
                        )
                        """
                    ),
                    {
                        "user_id": user_id,
                        "concept_id": concept_id,
                        "mastery_score": new_score,
                        "correct_count": correct_increment,
                        "last_tested_at": now,
                        "updated_at": now,
                    },
                )
                return {
                    "user_id": user_id,
                    "concept_id": concept_id,
                    "mastery_score": new_score,
                    "attempt_count": 1,
                    "correct_count": correct_increment,
                }

            current = float(existing["mastery_score"] or 0.0)
            next_score = compute_next_mastery_score(current, result_label)
            attempt_count = int(existing["attempt_count"] or 0) + 1
            correct_count = int(existing["correct_count"] or 0) + correct_increment
            session.execute(
                text(
                    """
                    UPDATE user_concept_mastery
                    SET mastery_score = :mastery_score,
                        attempt_count = :attempt_count,
                        correct_count = :correct_count,
                        last_tested_at = :last_tested_at,
                        updated_at = :updated_at
                    WHERE user_id = :user_id AND concept_id = :concept_id
                    """
                ),
                {
                    "user_id": user_id,
                    "concept_id": concept_id,
                    "mastery_score": next_score,
                    "attempt_count": attempt_count,
                    "correct_count": correct_count,
                    "last_tested_at": now,
                    "updated_at": now,
                },
            )
            return {
                "user_id": user_id,
                "concept_id": concept_id,
                "mastery_score": next_score,
                "attempt_count": attempt_count,
                "correct_count": correct_count,
            }


def _json_loads_safe(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _estimate_token_count(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text.split()) * 1.3))


def compute_next_mastery_score(current_score: float, result_label: str) -> float:
    result_key = (result_label or "incorrect").strip().lower()
    delta = -0.12
    if result_key == "correct":
        delta = 0.15
    elif result_key == "partial":
        delta = 0.05
    return max(0.0, min(1.0, float(current_score or 0.0) + delta))
