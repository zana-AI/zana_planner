from __future__ import annotations

import time
from dataclasses import replace
from typing import Any, Dict, Optional, Protocol, Sequence

from langchain_core.messages import BaseMessage

from .types import LLMInvokeOptions, NormalizedLLMResult, ProviderCapabilities
from .telemetry import record_usage_safely
from .usage import extract_model_name, extract_tokens

class ProviderAdapter(Protocol):
    name: str
    capabilities: ProviderCapabilities

    def build_role_model(self, role: str, base_config: Dict[str, Any]) -> Any:
        ...

    def invoke(
        self,
        model: Any,
        messages: Sequence[BaseMessage],
        options: LLMInvokeOptions,
        extra_kwargs: Optional[Dict[str, Any]] = None,
    ) -> NormalizedLLMResult:
        ...

    def normalize_content(self, content: Any) -> str:
        ...

    def supports(self, capability: str) -> bool:
        ...


class ProviderBoundModel:
    """Thin model wrapper carrying provider adapter + invoke options."""

    _zana_provider_wrapped = True

    def __init__(self, adapter: ProviderAdapter, model: Any, options: LLMInvokeOptions):
        self._adapter = adapter
        self._model = model
        self._options = options

    def invoke(self, messages: Sequence[BaseMessage], **kwargs: Any) -> Any:
        provider = getattr(self._adapter, "name", "unknown") or "unknown"
        model_name = extract_model_name(self._model, self._options)
        role = getattr(self._options, "purpose", None)
        start = time.perf_counter()
        try:
            result = self._adapter.invoke(
                model=self._model,
                messages=messages,
                options=self._options,
                extra_kwargs=kwargs or None,
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            error_type = type(exc).__name__
            _record_usage(
                provider=provider,
                model_name=model_name,
                role=role,
                input_tokens=0,
                output_tokens=0,
                latency_ms=latency_ms,
                success=False,
                error_type=error_type,
            )
            _emit_trace(
                provider=provider,
                model_name=model_name,
                role=role,
                messages_in=messages,
                output_text="",
                input_tokens=0,
                output_tokens=0,
                latency_ms=latency_ms,
                success=False,
                error_type=error_type,
            )
            raise
        latency_ms = int((time.perf_counter() - start) * 1000)
        in_tok, out_tok = extract_tokens(result.raw)
        _record_usage(
            provider=provider,
            model_name=model_name,
            role=role,
            input_tokens=in_tok,
            output_tokens=out_tok,
            latency_ms=latency_ms,
            success=True,
            error_type=None,
        )
        _emit_trace(
            provider=provider,
            model_name=model_name,
            role=role,
            messages_in=messages,
            output_text=getattr(result, "text", "") or "",
            input_tokens=in_tok,
            output_tokens=out_tok,
            latency_ms=latency_ms,
            success=True,
            error_type=None,
        )
        return result.raw

    def bind_tools(self, tools: Sequence[Any]) -> "ProviderBoundModel":
        bound = self._model.bind_tools(tools)
        return ProviderBoundModel(
            adapter=self._adapter,
            model=bound,
            options=replace(self._options, tools_enabled=True),
        )

    def __getattr__(self, item: str) -> Any:
        return getattr(self._model, item)


def wrap_model(adapter: ProviderAdapter, model: Any, options: LLMInvokeOptions) -> ProviderBoundModel:
    return ProviderBoundModel(adapter=adapter, model=model, options=options)


def _record_usage(
    *,
    provider: str,
    model_name: str,
    role: Optional[str],
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    success: bool,
    error_type: Optional[str],
) -> None:
    """Backward-compatible wrapper around shared best-effort telemetry."""
    record_usage_safely(
        provider=provider,
        model_name=model_name,
        role=role,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        success=success,
        error_type=error_type,
    )


def _emit_trace(**kwargs: Any) -> None:
    """Best-effort Langfuse trace emit; never raises.

    Imports are deferred so missing module / missing langfuse package /
    misconfigured env never blocks bot startup on a fresh server.
    """
    try:
        from .langfuse_client import trace_generation
        trace_generation(**kwargs)
    except Exception:  # pragma: no cover
        pass
