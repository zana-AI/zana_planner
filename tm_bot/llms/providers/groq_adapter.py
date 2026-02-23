from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI

from llms.model_policy import mark_rate_limited, pick_first_available, update_from_response_metadata
from .base import ProviderAdapter, wrap_model
from .types import LLMInvokeOptions, NormalizedLLMResult, ProviderCapabilities

try:
    from openai import RateLimitError as _OpenAIRateLimitError  # type: ignore
except Exception:  # pragma: no cover
    _OpenAIRateLimitError = None


class GroqProviderAdapter(ProviderAdapter):
    name = "groq"
    _TOOL_MISMATCH_BLOCK_SECONDS = 60.0
    CANDIDATE_MODELS = (
        "openai/gpt-oss-20b",
        "llama-3.3-70b-versatile",
    )

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

    @classmethod
    def _ordered_candidates(cls, requested_model: str) -> list[str]:
        candidates: list[str] = []
        requested = (requested_model or "").strip()
        if requested:
            candidates.append(requested)
        for model_name in cls.CANDIDATE_MODELS:
            if model_name not in candidates:
                candidates.append(model_name)
        return candidates

    def build_role_model(self, role: str, base_config: Dict[str, Any]) -> Any:
        role_temps = base_config.get("temperatures", {})
        requested_model = str(
            base_config.get("groq_model")
            or base_config.get("model_name")
            or self.CANDIDATE_MODELS[0]
        ).strip() or self.CANDIDATE_MODELS[0]
        candidates = self._ordered_candidates(requested_model)
        selected_model = pick_first_available("groq", candidates) or requested_model
        model = ChatOpenAI(
            openai_api_key=base_config.get("groq_api_key", ""),
            base_url=base_config.get("groq_base_url", "https://api.groq.com/openai/v1"),
            model=selected_model,
            temperature=float(role_temps.get(role, 0.2)),
            timeout=base_config.get("request_timeout_seconds"),
            max_retries=base_config.get("max_retries"),
            include_response_headers=True,
        )
        options = LLMInvokeOptions(
            purpose=role,
            structured_output=(role == "planner"),
            rich_features=str(base_config.get("feature_policy") or "safe"),
            metadata={"provider": "groq", "model": selected_model},
        )
        return wrap_model(self, model, options)

    @staticmethod
    def _model_name(model: Any, options: LLMInvokeOptions) -> str:
        for attr in ("model_name", "model"):
            value = getattr(model, attr, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
        meta_model = str((options.metadata or {}).get("model") or "").strip()
        return meta_model or "openai/gpt-oss-20b"

    @staticmethod
    def _extract_retry_after(exc: Exception) -> tuple[Optional[float], Optional[str]]:
        retry_after_s: Optional[float] = None
        reset_hint: Optional[str] = None

        for attr in ("retry_after", "retry_after_s"):
            value = getattr(exc, attr, None)
            if isinstance(value, (int, float)) and value > 0:
                retry_after_s = float(value)
                break
        retry_after_ms = getattr(exc, "retry_after_ms", None)
        if retry_after_s is None and isinstance(retry_after_ms, (int, float)) and retry_after_ms > 0:
            retry_after_s = float(retry_after_ms) / 1000.0

        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None) if response is not None else None
        if hasattr(headers, "get"):
            retry_after_header = headers.get("retry-after") or headers.get("Retry-After")
            if retry_after_header is not None:
                try:
                    retry_after_s = float(str(retry_after_header).strip())
                except ValueError:
                    reset_hint = str(retry_after_header)
            reset_hint = reset_hint or headers.get("x-ratelimit-reset-requests") or headers.get(
                "x-ratelimit-reset-tokens"
            )

        if reset_hint is not None:
            reset_hint = str(reset_hint)
        return retry_after_s, reset_hint

    @staticmethod
    def _is_rate_limited(exc: Exception) -> bool:
        if _OpenAIRateLimitError and isinstance(exc, _OpenAIRateLimitError):
            return True
        lower = str(exc or "").lower()
        return "429" in lower or "rate limit" in lower or "resource exhausted" in lower

    @staticmethod
    def _is_tool_choice_mismatch(exc: Exception) -> bool:
        lower = str(exc or "").lower()
        return "tool_use_failed" in lower or (
            "tool choice is none" in lower and "model called a tool" in lower
        )

    def invoke(
        self,
        model: Any,
        messages: Sequence[BaseMessage],
        options: LLMInvokeOptions,
        extra_kwargs: Optional[Dict[str, Any]] = None,
    ) -> NormalizedLLMResult:
        kwargs = dict(extra_kwargs or {})
        model_name = self._model_name(model, options)
        try:
            raw = model.invoke(messages, **kwargs)
        except Exception as exc:
            if self._is_rate_limited(exc):
                retry_after_s, reset_hint = self._extract_retry_after(exc)
                mark_rate_limited(
                    provider="groq",
                    model_id=model_name,
                    retry_after_s=retry_after_s,
                    reset_hint=reset_hint,
                )
            elif self._is_tool_choice_mismatch(exc):
                # Temporarily block models that emit tool calls for non-tool invocations.
                # This steers subsequent requests to the configured fallback model.
                mark_rate_limited(
                    provider="groq",
                    model_id=model_name,
                    retry_after_s=self._TOOL_MISMATCH_BLOCK_SECONDS,
                    reset_hint=None,
                )
            raise

        metadata = getattr(raw, "response_metadata", None) or {}
        update_from_response_metadata(
            provider="groq",
            model_id=model_name,
            response_metadata=metadata,
        )
        content = getattr(raw, "content", None)
        tool_calls = list(getattr(raw, "tool_calls", None) or [])
        finish_reason = metadata.get("finish_reason") if isinstance(metadata, dict) else None
        return NormalizedLLMResult(
            text=self.normalize_content(content),
            content_blocks=content if isinstance(content, list) else [],
            tool_calls=tool_calls,
            raw=raw,
            finish_reason=finish_reason,
        )
