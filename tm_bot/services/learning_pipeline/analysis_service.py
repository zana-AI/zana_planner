"""
Summary and concept extraction service.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple

from services.learning_pipeline.llm_gateway import LearningLLMGateway
from utils.logger import get_logger

logger = get_logger(__name__)

_STOPWORDS = {
    "the",
    "and",
    "that",
    "with",
    "this",
    "from",
    "have",
    "will",
    "your",
    "about",
    "into",
    "also",
    "they",
    "their",
    "there",
    "were",
    "which",
    "because",
    "would",
    "what",
    "when",
    "where",
    "while",
    "been",
    "being",
    "could",
    "should",
    "than",
    "them",
    "these",
    "those",
    "some",
    "more",
    "most",
    "many",
    "such",
    "only",
    "over",
    "under",
    "between",
    "after",
    "before",
    "across",
    "through",
    "using",
    "used",
    "use",
}


class AnalysisService:
    def __init__(self) -> None:
        self.llm = LearningLLMGateway()

    def generate_summaries(self, segments: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], bool, str]:
        segment_summaries = self._segment_summaries(segments)
        section_summaries = self._section_summaries(segments)
        full_text = _build_text_for_llm(segments, max_chars=12000)

        global_summary = self._fallback_global_summary(segment_summaries)
        model_name = "heuristic"
        used_fallback = False

        if full_text and self.llm.available():
            try:
                prompt = (
                    "You are producing structured study notes.\n"
                    "Return strict JSON with keys: summary, key_takeaways (array of strings), misconceptions (array), definitions (array of objects with term and definition).\n\n"
                    f"Content:\n{full_text}"
                )
                raw, model_name, used_fallback = self.llm.invoke(prompt)
                parsed = _parse_json_output(raw)
                if isinstance(parsed, dict) and parsed.get("summary"):
                    global_summary = {
                        "summary": str(parsed.get("summary")),
                        "key_takeaways": _as_str_list(parsed.get("key_takeaways")),
                        "misconceptions": _as_str_list(parsed.get("misconceptions")),
                        "definitions": parsed.get("definitions") if isinstance(parsed.get("definitions"), list) else [],
                    }
            except Exception as exc:
                logger.warning("LLM global summary failed: %s", exc)

        return (
            {
                "summary_segment": {"items": segment_summaries},
                "summary_section": {"items": section_summaries},
                "summary_global": global_summary,
            },
            used_fallback,
            model_name,
        )

    def extract_concepts(self, segments: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], bool, str]:
        full_text = _build_text_for_llm(segments, max_chars=12000)
        llm_concepts: List[Dict[str, Any]] = []
        llm_edges: List[Dict[str, Any]] = []
        model_name = "heuristic"
        used_fallback = False

        if full_text and self.llm.available():
            try:
                prompt = (
                    "Extract concept graph for study.\n"
                    "Return strict JSON object with keys: concepts (array) and edges (array).\n"
                    "Concept shape: {label, concept_type, definition, examples}\n"
                    "Edge shape: {source, relation_type, target, confidence}\n"
                    "Keep 8-20 concepts and relation_type among prerequisite_of, explains, contrasts_with, part_of, causes, used_for, related_to.\n\n"
                    f"Content:\n{full_text}"
                )
                raw, model_name, used_fallback = self.llm.invoke(prompt)
                parsed = _parse_json_output(raw)
                if isinstance(parsed, dict):
                    llm_concepts = parsed.get("concepts") if isinstance(parsed.get("concepts"), list) else []
                    llm_edges = parsed.get("edges") if isinstance(parsed.get("edges"), list) else []
            except Exception as exc:
                logger.warning("LLM concept extraction failed: %s", exc)

        concepts, edges = self._normalize_or_fallback_concepts(segments, llm_concepts, llm_edges)
        weighted = _compute_weights(concepts, edges, segments)
        return {"concepts": weighted, "edges": edges}, used_fallback, model_name

    def _segment_summaries(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for segment in segments:
            text = (segment.get("text") or "").strip()
            if not text:
                continue
            summary = _first_sentence(text, limit=220)
            items.append(
                {
                    "segment_id": segment.get("id"),
                    "segment_index": segment.get("segment_index"),
                    "summary": summary,
                }
            )
        return items

    def _section_summaries(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        by_section: Dict[str, List[str]] = defaultdict(list)
        for segment in segments:
            section = str(segment.get("section_path") or "content").strip() or "content"
            text = (segment.get("text") or "").strip()
            if text:
                by_section[section].append(text)
        result: List[Dict[str, Any]] = []
        for section, texts in by_section.items():
            merged = " ".join(texts)
            result.append({"section_path": section, "summary": _first_sentence(merged, limit=320)})
        return result

    def _fallback_global_summary(self, segment_summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
        top = [item["summary"] for item in segment_summaries[:5] if item.get("summary")]
        summary = " ".join(top).strip()
        if not summary:
            summary = "No summary available."
        return {
            "summary": summary[:900],
            "key_takeaways": top[:5],
            "misconceptions": [],
            "definitions": [],
        }

    def _normalize_or_fallback_concepts(
        self,
        segments: List[Dict[str, Any]],
        llm_concepts: List[Dict[str, Any]],
        llm_edges: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        concepts: List[Dict[str, Any]] = []
        seen = set()
        for concept in llm_concepts:
            label = str(concept.get("label") or "").strip()
            if not label:
                continue
            key = label.lower()
            if key in seen:
                continue
            seen.add(key)
            concepts.append(
                {
                    "label": label,
                    "concept_type": concept.get("concept_type") or "topic",
                    "definition": concept.get("definition") or "",
                    "examples": concept.get("examples") if isinstance(concept.get("examples"), list) else [],
                }
            )

        if len(concepts) < 5:
            freq = _top_terms_from_segments(segments, top_n=14)
            concepts = []
            for term, count in freq:
                concepts.append(
                    {
                        "label": term,
                        "concept_type": "topic",
                        "definition": "",
                        "examples": _examples_for_term(term, segments),
                        "support_count": count,
                    }
                )

        label_set = {item["label"].lower() for item in concepts}
        edges: List[Dict[str, Any]] = []
        for edge in llm_edges:
            source = str(edge.get("source") or "").strip()
            target = str(edge.get("target") or "").strip()
            if not source or not target:
                continue
            if source.lower() not in label_set or target.lower() not in label_set:
                continue
            edges.append(
                {
                    "source": source,
                    "target": target,
                    "relation_type": edge.get("relation_type") or edge.get("relation") or "related_to",
                    "confidence": float(edge.get("confidence") or 0.5),
                    "weight": float(edge.get("weight") or edge.get("confidence") or 0.5),
                }
            )

        if not edges:
            for idx in range(len(concepts) - 1):
                edges.append(
                    {
                        "source": concepts[idx]["label"],
                        "target": concepts[idx + 1]["label"],
                        "relation_type": "related_to",
                        "confidence": 0.6,
                        "weight": 0.6,
                    }
                )
        return concepts, edges


def _compute_weights(
    concepts: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    segments: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    text_blob = " ".join((segment.get("text") or "").lower() for segment in segments)
    freq_counter = Counter(re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text_blob))
    mention_raw: Dict[str, float] = {}
    degree_raw: Dict[str, float] = defaultdict(float)
    confidence_raw: Dict[str, float] = defaultdict(float)
    confidence_count: Dict[str, int] = defaultdict(int)

    for concept in concepts:
        label = concept.get("label") or ""
        key = str(label).lower()
        mention_raw[key] = float(freq_counter.get(key, concept.get("support_count") or 1))

    for edge in edges:
        source = str(edge.get("source") or "").lower()
        target = str(edge.get("target") or "").lower()
        confidence = float(edge.get("confidence") or edge.get("weight") or 0.0)
        degree_raw[source] += 1.0
        degree_raw[target] += 1.0
        confidence_raw[source] += confidence
        confidence_raw[target] += confidence
        confidence_count[source] += 1
        confidence_count[target] += 1

    mention_norm = _normalize_map(mention_raw)
    degree_norm = _normalize_map(degree_raw)
    confidence_mean = {
        key: (confidence_raw[key] / confidence_count[key]) if confidence_count[key] else 0.0
        for key in set(list(confidence_raw.keys()) + list(mention_raw.keys()))
    }
    confidence_norm = _normalize_map(confidence_mean)

    output = []
    for concept in concepts:
        key = str(concept.get("label") or "").lower()
        importance = 0.4 * mention_norm.get(key, 0.0) + 0.3 * degree_norm.get(key, 0.0) + 0.3 * confidence_norm.get(key, 0.0)
        output.append(
            {
                **concept,
                "support_count": int(mention_raw.get(key, 0)),
                "importance_weight": round(float(importance), 6),
            }
        )
    output.sort(key=lambda item: item.get("importance_weight", 0.0), reverse=True)
    return output


def _normalize_map(raw: Dict[str, float]) -> Dict[str, float]:
    if not raw:
        return {}
    values = list(raw.values())
    min_value = min(values)
    max_value = max(values)
    if max_value <= min_value:
        return {key: 0.5 for key in raw}
    return {key: (value - min_value) / (max_value - min_value) for key, value in raw.items()}


def _build_text_for_llm(segments: List[Dict[str, Any]], max_chars: int) -> str:
    text_parts = []
    current_len = 0
    for segment in segments:
        text_value = (segment.get("text") or "").strip()
        if not text_value:
            continue
        block = text_value + "\n\n"
        if current_len + len(block) > max_chars:
            break
        text_parts.append(block)
        current_len += len(block)
    return "".join(text_parts).strip()


def _parse_json_output(raw: str) -> Any:
    value = (raw or "").strip()
    if not value:
        return {}
    fenced = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", value, flags=re.DOTALL)
    if fenced:
        value = fenced.group(1).strip()
    try:
        return json.loads(value)
    except Exception:
        match = re.search(r"(\{.*\})", value, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                return {}
        return {}


def _as_str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def _first_sentence(text: str, limit: int = 220) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    if not cleaned:
        return ""
    chunks = re.split(r"(?<=[.!?])\s+", cleaned)
    sentence = chunks[0] if chunks else cleaned
    if len(sentence) <= limit:
        return sentence
    return sentence[: limit - 3].rstrip() + "..."


def _top_terms_from_segments(segments: List[Dict[str, Any]], top_n: int = 12) -> List[Tuple[str, int]]:
    blob = " ".join((segment.get("text") or "") for segment in segments).lower()
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", blob)
    filtered = [word for word in words if word not in _STOPWORDS]
    counter = Counter(filtered)
    return counter.most_common(top_n)


def _examples_for_term(term: str, segments: List[Dict[str, Any]]) -> List[str]:
    needle = term.lower()
    examples = []
    for segment in segments:
        text = (segment.get("text") or "").strip()
        if needle in text.lower():
            examples.append(_first_sentence(text, limit=140))
        if len(examples) >= 2:
            break
    return examples
