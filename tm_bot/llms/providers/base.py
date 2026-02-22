from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Optional, Protocol, Sequence

from langchain_core.messages import BaseMessage

from .types import LLMInvokeOptions, NormalizedLLMResult, ProviderCapabilities


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
        result = self._adapter.invoke(
            model=self._model,
            messages=messages,
            options=self._options,
            extra_kwargs=kwargs or None,
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

