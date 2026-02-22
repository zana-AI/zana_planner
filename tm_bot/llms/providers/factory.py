from __future__ import annotations

from typing import Any, Dict

from .base import ProviderAdapter
from .gemini_adapter import GeminiProviderAdapter
from .openai_adapter import OpenAIProviderAdapter


def create_provider_adapter(cfg: Dict[str, Any]) -> ProviderAdapter:
    provider = str(cfg.get("LLM_PROVIDER") or "auto").strip().lower()

    if provider == "auto":
        if cfg.get("GCP_PROJECT_ID"):
            provider = "gemini"
        elif cfg.get("OPENAI_API_KEY"):
            provider = "openai"
        else:
            raise ValueError("LLM_PROVIDER=auto but no provider credentials were found")

    if provider in {"gemini", "google"}:
        return GeminiProviderAdapter(cfg)
    if provider == "openai":
        return OpenAIProviderAdapter(cfg)

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")

