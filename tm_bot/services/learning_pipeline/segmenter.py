"""
Segment normalization and chunking for embeddings/retrieval.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List

from services.learning_pipeline.types import SegmentRecord

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except Exception:
    RecursiveCharacterTextSplitter = None


class Segmenter:
    def __init__(self, chunk_size: int = 1200, chunk_overlap: int = 180):
        self.chunk_size = int(chunk_size)
        self.chunk_overlap = int(chunk_overlap)

    def segment_text(self, text: str, section_path: str | None = None) -> List[SegmentRecord]:
        cleaned = (text or "").strip()
        if not cleaned:
            return []
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", cleaned) if p.strip()]
        if not paragraphs:
            paragraphs = [cleaned]
        records: List[SegmentRecord] = []
        for paragraph in paragraphs:
            for part in _split_long_block(paragraph, self.chunk_size):
                records.append(SegmentRecord(text=part, section_path=section_path, token_count=_estimate_tokens(part)))
        return records

    def build_chunks(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not segments:
            return []
        chunks: List[Dict[str, Any]] = []
        if RecursiveCharacterTextSplitter:
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                separators=["\n\n", "\n", ". ", " ", ""],
            )
            for segment in segments:
                segment_text = (segment.get("text") or "").strip()
                if not segment_text:
                    continue
                split_items = splitter.split_text(segment_text)
                for idx, chunk_text in enumerate(split_items):
                    chunks.append(
                        {
                            "chunk_id": str(uuid.uuid4()),
                            "segment_id": segment.get("id"),
                            "segment_index": segment.get("segment_index"),
                            "chunk_index": idx,
                            "text": chunk_text,
                            "start_ms": segment.get("start_ms"),
                            "end_ms": segment.get("end_ms"),
                            "section_path": segment.get("section_path"),
                        }
                    )
            return chunks

        for segment in segments:
            segment_text = (segment.get("text") or "").strip()
            if not segment_text:
                continue
            for idx, chunk_text in enumerate(_split_long_block(segment_text, self.chunk_size)):
                chunks.append(
                    {
                        "chunk_id": str(uuid.uuid4()),
                        "segment_id": segment.get("id"),
                        "segment_index": segment.get("segment_index"),
                        "chunk_index": idx,
                        "text": chunk_text,
                        "start_ms": segment.get("start_ms"),
                        "end_ms": segment.get("end_ms"),
                        "section_path": segment.get("section_path"),
                    }
                )
        return chunks


def _split_long_block(text: str, max_chars: int) -> List[str]:
    content = (text or "").strip()
    if len(content) <= max_chars:
        return [content]
    words = content.split()
    items: List[str] = []
    current: List[str] = []
    current_len = 0
    for word in words:
        next_len = current_len + len(word) + (1 if current else 0)
        if next_len > max_chars and current:
            items.append(" ".join(current).strip())
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len = next_len
    if current:
        items.append(" ".join(current).strip())
    return [item for item in items if item]


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text.split()) * 1.3))
