from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI

from .base import ProviderAdapter, wrap_model
from .types import LLMInvokeOptions, NormalizedLLMResult, ProviderCapabilities


class OpenAIProviderAdapter(ProviderAdapter):
    name = "openai"

    def __init__(self, cfg: Dict[str, Any]):
        self._cfg = cfg
        self.capabilities = ProviderCapabilities(
            supports_structured_output=False,
            supports_native_tool_calls=True,
            supports_reasoning_controls=False,
            supports_thought_controls=False,
        )

    def supports(self, capability: str) -> bool:
        return bool(getattr(self.capabilities, capability, False))

    def normalize_content(self, content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            out = []
            for block in content:
                if isinstance(block, str):
                    out.append(block)
                elif isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str):
                        out.append(text)
            return "\n".join(out)
        if isinstance(content, dict):
            text = content.get("text")
            if isinstance(text, str):
                return text
        return str(content)

    def build_role_model(self, role: str, base_config: Dict[str, Any]) -> Any:
        role_temps = base_config.get("temperatures", {})
        model = ChatOpenAI(
            openai_api_key=base_config.get("openai_api_key", ""),
            model=base_config.get("openai_model", "gpt-4o-mini"),
            temperature=float(role_temps.get(role, 0.2)),
            timeout=base_config.get("request_timeout_seconds"),
            max_retries=base_config.get("max_retries"),
        )
        options = LLMInvokeOptions(
            purpose=role,
            structured_output=(role == "planner"),
            rich_features=str(base_config.get("feature_policy") or "safe"),
        )
        return wrap_model(self, model, options)

    def invoke(
        self,
        model: Any,
        messages: Sequence[BaseMessage],
        options: LLMInvokeOptions,
        extra_kwargs: Optional[Dict[str, Any]] = None,
    ) -> NormalizedLLMResult:
        kwargs = dict(extra_kwargs or {})
        raw = model.invoke(messages, **kwargs)
        content = getattr(raw, "content", None)
        tool_calls = list(getattr(raw, "tool_calls", None) or [])
        metadata = getattr(raw, "response_metadata", None) or {}
        finish_reason = metadata.get("finish_reason") if isinstance(metadata, dict) else None
        return NormalizedLLMResult(
            text=self.normalize_content(content),
            content_blocks=content if isinstance(content, list) else [],
            tool_calls=tool_calls,
            raw=raw,
            finish_reason=finish_reason,
        )

