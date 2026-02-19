"""
Quiz generation and grading service.
"""

from __future__ import annotations

import json
import random
import re
from typing import Any, Dict, List, Optional, Tuple

from services.learning_pipeline.learning_repo import LearningPipelineRepository
from services.learning_pipeline.llm_gateway import LearningLLMGateway
from utils.logger import get_logger

logger = get_logger(__name__)


class QuizService:
    def __init__(self, learning_repo: Optional[LearningPipelineRepository] = None) -> None:
        self.repo = learning_repo or LearningPipelineRepository()
        self.llm = LearningLLMGateway()

    def create_quiz(
        self,
        content_id: str,
        difficulty: str = "medium",
        question_count: int = 8,
    ) -> Tuple[Dict[str, Any], bool]:
        difficulty = (difficulty or "medium").strip().lower()
        question_count = max(1, min(int(question_count or 8), 20))
        graph = self.repo.get_concepts_graph(content_id)
        concepts = graph.get("nodes") or []
        edges = graph.get("edges") or []
        segments = self.repo.list_segments(content_id)

        questions, fallback_used = self._build_questions(concepts, edges, segments, difficulty, question_count)
        concept_map = {str(node.get("label") or "").lower(): str(node.get("id")) for node in concepts if node.get("id")}
        quiz = self.repo.create_quiz_set(
            content_id=content_id,
            title="Content quiz",
            difficulty=difficulty,
            questions=questions,
            concept_id_by_label=concept_map,
        )
        return {
            "quiz_set_id": quiz["quiz_set_id"],
            "questions": _public_questions(quiz["questions"]),
            "difficulty": difficulty,
        }, fallback_used

    def submit_answers(
        self,
        user_id: str,
        quiz_set_id: str,
        answers: List[Dict[str, Any]],
        idempotency_key: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], bool]:
        fallback_used = False
        existing_attempt = None
        if idempotency_key:
            existing_attempt = self.repo.find_attempt_by_idempotency(user_id, quiz_set_id, idempotency_key)
            if existing_attempt and existing_attempt.get("status") == "graded":
                report = self.repo.get_attempt_report(existing_attempt["id"])
                if report:
                    return _report_to_response(report, mastery_updates=[]), False

        questions = self.repo.get_quiz_questions(quiz_set_id)
        question_by_id = {str(question["id"]): question for question in questions}
        attempt_id = self.repo.create_attempt(user_id=user_id, quiz_set_id=quiz_set_id, idempotency_key=idempotency_key)

        graded_answers = []
        per_question_feedback = []
        mastery_updates = []
        total_score = 0.0
        max_score = float(len(questions))

        answers_by_question = {str(item.get("question_id")): item for item in (answers or []) if item.get("question_id")}
        for question in questions:
            question_id = str(question["id"])
            submitted = answers_by_question.get(question_id, {})
            user_answer = submitted.get("answer")
            result_label, score_awarded, feedback, used_fallback_local, graded_by_model = self._grade_single(question, user_answer)
            fallback_used = fallback_used or used_fallback_local
            total_score += score_awarded

            graded_answers.append(
                {
                    "question_id": question_id,
                    "user_answer_json": {"answer": user_answer},
                    "is_correct": result_label == "correct",
                    "score_awarded": score_awarded,
                    "feedback": feedback,
                    "graded_by_model": graded_by_model,
                }
            )
            per_question_feedback.append(
                {
                    "question_id": question_id,
                    "result": result_label,
                    "score_awarded": score_awarded,
                    "feedback": feedback,
                }
            )

            concept_id = question.get("concept_id")
            if concept_id:
                mastery = self.repo.apply_mastery_result(user_id=str(user_id), concept_id=str(concept_id), result_label=result_label)
                mastery_updates.append(mastery)

        self.repo.finalize_attempt(
            attempt_id=attempt_id,
            score=total_score,
            max_score=max_score,
            answers=graded_answers,
        )
        report = self.repo.get_attempt_report(attempt_id)
        response = _report_to_response(report, mastery_updates=mastery_updates)
        response["per_question_feedback"] = per_question_feedback
        return response, fallback_used

    def _build_questions(
        self,
        concepts: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        segments: List[Dict[str, Any]],
        difficulty: str,
        question_count: int,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        if self.llm.available():
            try:
                prompt = (
                    "Generate study quiz questions from concepts.\n"
                    "Return strict JSON array of objects with keys: concept_label, question_type, difficulty, prompt, options, answer_key, rationale, source_segment_ids.\n"
                    f"Difficulty: {difficulty}\n"
                    f"Count: {question_count}\n"
                    f"Concepts: {json.dumps([{ 'label': c.get('label'), 'definition': c.get('definition'), 'importance_weight': c.get('importance_weight')} for c in concepts[:20]])}\n"
                    f"Edges: {json.dumps(edges[:40])}\n"
                )
                raw, _, used_fallback = self.llm.invoke(prompt)
                parsed = _parse_json(raw)
                if isinstance(parsed, list):
                    normalized = [_normalize_question(item, idx + 1) for idx, item in enumerate(parsed)]
                    normalized = [item for item in normalized if item]
                    if normalized:
                        return normalized[:question_count], used_fallback
            except Exception as exc:
                logger.warning("LLM quiz generation failed: %s", exc)

        return _heuristic_questions(concepts, segments, difficulty, question_count), False

    def _grade_single(self, question: Dict[str, Any], user_answer: Any) -> Tuple[str, float, str, bool, str]:
        question_type = str(question.get("question_type") or "mcq").strip().lower()
        answer_key = question.get("answer_key_json") or {}
        if not isinstance(answer_key, dict):
            answer_key = {}
        normalized = _norm(str(user_answer or ""))

        if question_type in ("mcq", "cloze"):
            accepted = answer_key.get("accepted_answers")
            if not isinstance(accepted, list):
                accepted = [answer_key.get("correct_option"), answer_key.get("answer"), answer_key.get("correct_answer")]
            accepted_norm = {_norm(str(item or "")) for item in accepted if item}
            if normalized and normalized in accepted_norm:
                return "correct", 1.0, "Correct.", False, "heuristic"
            if normalized and any(normalized in choice or choice in normalized for choice in accepted_norm if choice):
                return "partial", 0.5, "Partially correct.", False, "heuristic"
            return "incorrect", 0.0, "Incorrect.", False, "heuristic"

        # short answer grading
        expected = answer_key.get("answer") or answer_key.get("expected_answer") or answer_key.get("rubric") or ""
        if not expected:
            return "incorrect", 0.0, "No answer key available.", False, "heuristic"

        if self.llm.available():
            try:
                prompt = (
                    "Grade a short answer against expected answer.\n"
                    "Return strict JSON: {result: correct|partial|incorrect, feedback: string}.\n"
                    f"Question: {question.get('prompt')}\n"
                    f"Expected answer: {expected}\n"
                    f"User answer: {user_answer}"
                )
                raw, _, used_fallback = self.llm.invoke(prompt)
                parsed = _parse_json(raw)
                if isinstance(parsed, dict):
                    result_label = str(parsed.get("result") or "incorrect").strip().lower()
                    if result_label not in ("correct", "partial", "incorrect"):
                        result_label = "incorrect"
                    score = 1.0 if result_label == "correct" else 0.5 if result_label == "partial" else 0.0
                    return result_label, score, str(parsed.get("feedback") or "Graded by model."), used_fallback, "llm"
            except Exception as exc:
                logger.warning("LLM short-answer grading failed: %s", exc)

        # lexical fallback
        expected_terms = set(re.findall(r"[a-zA-Z0-9_]{3,}", _norm(str(expected))))
        answer_terms = set(re.findall(r"[a-zA-Z0-9_]{3,}", normalized))
        overlap = len(expected_terms.intersection(answer_terms))
        ratio = overlap / max(1, len(expected_terms))
        if ratio >= 0.6:
            return "correct", 1.0, "Answer matches expected key points.", False, "heuristic"
        if ratio >= 0.3:
            return "partial", 0.5, "Answer captures some key points.", False, "heuristic"
        return "incorrect", 0.0, "Answer does not match expected key points.", False, "heuristic"


def _heuristic_questions(
    concepts: List[Dict[str, Any]],
    segments: List[Dict[str, Any]],
    difficulty: str,
    question_count: int,
) -> List[Dict[str, Any]]:
    top_concepts = concepts[: max(4, question_count)]
    labels = [str(concept.get("label") or "").strip() for concept in top_concepts if concept.get("label")]
    questions: List[Dict[str, Any]] = []
    for idx, label in enumerate(labels[:question_count]):
        distractors = [item for item in labels if item != label][:3]
        options = [label] + distractors
        random.Random(idx + len(label)).shuffle(options)
        segment_ids = []
        for segment in segments:
            if label.lower() in str(segment.get("text") or "").lower():
                segment_ids.append(segment.get("id"))
            if len(segment_ids) >= 2:
                break
        questions.append(
            {
                "position": idx + 1,
                "concept_label": label,
                "question_type": "mcq",
                "difficulty": difficulty,
                "prompt": f"Which concept is central to this content: {label}?",
                "options": options,
                "answer_key": {"correct_option": label, "accepted_answers": [label]},
                "rationale": f"{label} appears frequently in the source content.",
                "source_segment_ids": [sid for sid in segment_ids if sid],
            }
        )
    return questions


def _normalize_question(question: Any, position: int) -> Dict[str, Any]:
    if not isinstance(question, dict):
        return {}
    prompt = str(question.get("prompt") or "").strip()
    if not prompt:
        return {}
    concept_label = str(question.get("concept_label") or "").strip()
    question_type = str(question.get("question_type") or "mcq").strip().lower()
    if question_type not in ("mcq", "short_answer", "cloze"):
        question_type = "mcq"
    options = question.get("options") if isinstance(question.get("options"), list) else []
    answer_key = question.get("answer_key") if isinstance(question.get("answer_key"), dict) else {}
    source_segment_ids = question.get("source_segment_ids") if isinstance(question.get("source_segment_ids"), list) else []
    return {
        "position": int(question.get("position") or position),
        "concept_label": concept_label,
        "question_type": question_type,
        "difficulty": str(question.get("difficulty") or "medium"),
        "prompt": prompt,
        "options": options,
        "answer_key": answer_key,
        "rationale": str(question.get("rationale") or ""),
        "source_segment_ids": source_segment_ids,
    }


def _parse_json(raw: str) -> Any:
    value = (raw or "").strip()
    if not value:
        return []
    code_match = re.search(r"```(?:json)?\s*(\[.*\]|\{.*\})\s*```", value, flags=re.DOTALL)
    if code_match:
        value = code_match.group(1).strip()
    try:
        return json.loads(value)
    except Exception:
        return []


def _public_questions(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for question in questions:
        out.append(
            {
                "question_id": question.get("id"),
                "question_type": question.get("question_type"),
                "difficulty": question.get("difficulty"),
                "prompt": question.get("prompt"),
                "options": question.get("options") or [],
                "source_segment_ids": question.get("source_segment_ids") or [],
            }
        )
    return out


def _report_to_response(report: Optional[Dict[str, Any]], mastery_updates: List[Dict[str, Any]]) -> Dict[str, Any]:
    report = report or {}
    answers = report.get("answers") if isinstance(report.get("answers"), list) else []
    per_question_feedback = []
    for answer in answers:
        per_question_feedback.append(
            {
                "question_id": answer.get("question_id"),
                "result": "correct" if answer.get("is_correct") else "incorrect",
                "score_awarded": answer.get("score_awarded"),
                "feedback": answer.get("feedback"),
            }
        )
    return {
        "attempt_id": report.get("id"),
        "score": float(report.get("score") or 0.0),
        "max_score": float(report.get("max_score") or 0.0),
        "per_question_feedback": per_question_feedback,
        "mastery_updates": mastery_updates,
    }


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())
