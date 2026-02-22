from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from llms.genai_patches import apply_genai_patches
from .base import ProviderAdapter, wrap_model
from .types import LLMInvokeOptions, NormalizedLLMResult, ProviderCapabilities


class GeminiProviderAdapter(ProviderAdapter):
    name = "gemini"

    def __init__(self, cfg: Dict[str, Any]):
        apply_genai_patches()
        self._cfg = cfg
        self.capabilities = ProviderCapabilities(
            supports_structured_output=True,
            supports_native_tool_calls=True,
            supports_reasoning_controls=True,
            supports_thought_controls=True,
        )

    def supports(self, capability: str) -> bool:
        return bool(getattr(self.capabilities, capability, False))

    def normalize_content(self, content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                    continue
                if not isinstance(block, dict):
                    continue
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text)
            return "\n".join(parts)
        if isinstance(content, dict):
            text = content.get("text")
            if isinstance(text, str):
                return text
        return str(content)

    def build_role_model(self, role: str, base_config: Dict[str, Any]) -> Any:
        role_temps = base_config.get("temperatures", {})
        kwargs: Dict[str, Any] = {
            "model": base_config["model_name"],
            "project": base_config["project_id"],
            "location": base_config["llm_location"],
            "request_timeout": base_config["request_timeout_seconds"],
            "retries": base_config["max_retries"],
            "temperature": float(role_temps.get(role, 0.2)),
        }

        feature_policy = str(base_config.get("feature_policy") or "safe")
        include_thoughts = bool(base_config.get("include_thoughts", False))
        thinking_level = base_config.get("thinking_level")

        if feature_policy == "safe":
            kwargs["include_thoughts"] = False
        else:
            kwargs["include_thoughts"] = include_thoughts

        if feature_policy != "safe" and thinking_level:
            kwargs["thinking_level"] = thinking_level

        if role == "planner":
            planner_schema = base_config.get("planner_response_schema")
            if planner_schema:
                kwargs["response_mime_type"] = "application/json"
                kwargs["response_schema"] = planner_schema

        model = ChatGoogleGenerativeAI(**kwargs)
        options = LLMInvokeOptions(
            purpose=role,
            structured_output=(role == "planner"),
            rich_features=feature_policy,
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

        disable_afc = bool(self._cfg.get("GEMINI_DISABLE_AFC", True))
        if disable_afc:
            kwargs.setdefault("automatic_function_calling", {"disable": True})

        if str(options.rich_features or "safe") == "safe":
            kwargs.setdefault("include_thoughts", False)

        try:
            raw = model.invoke(messages, **kwargs)
        except TypeError:
            raw = model.invoke(messages)

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

