"""
Shared datatypes for learning pipeline stages.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SegmentRecord:
    text: str
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    section_path: Optional[str] = None
    token_count: Optional[int] = None


@dataclass
class IngestedContent:
    source_type: str
    language: Optional[str]
    text: str
    segments: List[SegmentRecord] = field(default_factory=list)
    assets: List[Dict[str, Any]] = field(default_factory=list)
    needs_transcription: bool = False
    audio_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
