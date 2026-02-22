from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ProviderCapabilities:
    supports_structured_output: bool = False
    supports_native_tool_calls: bool = True
    supports_reasoning_controls: bool = False
    supports_thought_controls: bool = False


@dataclass(frozen=True)
class LLMInvokeOptions:
    purpose: str
    structured_output: bool = False
    tools_enabled: bool = False
    rich_features: str = "safe"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedLLMResult:
    text: str
    content_blocks: List[Any]
    tool_calls: List[Dict[str, Any]]
    raw: Any
    finish_reason: Optional[str] = None

