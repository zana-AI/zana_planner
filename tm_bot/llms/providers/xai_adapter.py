from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .base import ProviderAdapter, wrap_model
from .types import LLMInvokeOptions, NormalizedLLMResult, ProviderCapabilities


class _XAIResponsesWebSearchModel:
    """Minimal xAI Responses API model for native web search turns."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout: Optional[float],
        max_retries: Optional[int],
    ) -> None:
        self.model = model
        self.model_name = model
        self._api_key = api_key
        self._base_url = (base_url or "https://api.x.ai/v1").rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries

    @staticmethod
    def _message_role(message: BaseMessage) -> str:
        if isinstance(message, SystemMessage):
            return "system"
        if isinstance(message, AIMessage):
            return "assistant"
        if isinstance(message, HumanMessage):
            return "user"
        return "user"

    @staticmethod
    def _content_to_text(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    text = block.get("text") or block.get("content")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(parts)
        return str(content)

    @classmethod
    def _messages_to_input(cls, messages: Sequence[BaseMessage]) -> List[Dict[str, str]]:
        items: List[Dict[str, str]] = []
        for message in messages:
            text = cls._content_to_text(getattr(message, "content", None)).strip()
            if not text:
                continue
            items.append({"role": cls._message_role(message), "content": text})
        return items

    @staticmethod
    def _response_to_text(response: Any) -> str:
        direct = getattr(response, "output_text", None)
        if isinstance(direct, str) and direct.strip():
            return direct
        if isinstance(response, dict):
            direct = response.get("output_text")
            if isinstance(direct, str) and direct.strip():
                return direct
            output = response.get("output") or []
        else:
            output = getattr(response, "output", None) or []

        parts: List[str] = []
        for item in output:
            content = item.get("content") if isinstance(item, dict) else getattr(item, "content", None)
            for block in content or []:
                if isinstance(block, dict):
                    text = block.get("text")
                else:
                    text = getattr(block, "text", None)
                if isinstance(text, str) and text.strip():
                    parts.append(text)
        return "\n".join(parts)

    @staticmethod
    def _usage_metadata(response: Any) -> Dict[str, int]:
        usage = response.get("usage") if isinstance(response, dict) else getattr(response, "usage", None)
        if usage is None:
            return {}

        def _get(name: str) -> int:
            value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return 0

        input_tokens = _get("input_tokens")
        output_tokens = _get("output_tokens")
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }

    def invoke(self, messages: Sequence[BaseMessage], **_: Any) -> AIMessage:
        from openai import OpenAI

        client_kwargs: Dict[str, Any] = {
            "api_key": self._api_key,
            "base_url": self._base_url,
        }
        if self._timeout is not None:
            client_kwargs["timeout"] = self._timeout
        if self._max_retries is not None:
            client_kwargs["max_retries"] = self._max_retries
        client = OpenAI(**client_kwargs)

        response = client.responses.create(
            model=self.model,
            input=self._messages_to_input(messages),
            tools=[{"type": "web_search"}],
        )
        usage_metadata = self._usage_metadata(response)
        response_metadata = {
            "id": getattr(response, "id", None),
            "model": getattr(response, "model", self.model),
            "usage_metadata": usage_metadata,
        }
        return AIMessage(
            content=self._response_to_text(response),
            response_metadata=response_metadata,
            usage_metadata=usage_metadata or None,
        )


class XAIProviderAdapter(ProviderAdapter):
    """OpenAI-compatible adapter for xAI Grok models."""

    name = "xai"

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
        kwargs: Dict[str, Any] = dict(
            openai_api_key=base_config.get("xai_api_key", ""),
            base_url=base_config.get("xai_base_url", "https://api.x.ai/v1"),
            model=base_config.get("xai_model") or base_config.get("model_name") or "grok-4.3",
            temperature=float(role_temps.get(role, 0.2)),
            timeout=base_config.get("request_timeout_seconds"),
            max_retries=base_config.get("max_retries"),
        )
        if base_config.get("live_search"):
            model = _XAIResponsesWebSearchModel(
                api_key=kwargs["openai_api_key"],
                base_url=kwargs["base_url"],
                model=kwargs["model"],
                timeout=kwargs["timeout"],
                max_retries=kwargs["max_retries"],
            )
        else:
            model = ChatOpenAI(**kwargs)
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
