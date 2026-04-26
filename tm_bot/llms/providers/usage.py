"""Helpers for extracting token usage and model identity from LangChain results."""
from __future__ import annotations

from typing import Any, Tuple

from .types import LLMInvokeOptions


def extract_model_name(model: Any, options: LLMInvokeOptions) -> str:
    """Best-effort model name from a LangChain chat model + invoke options."""
    for attr in ("model_name", "model"):
        value = getattr(model, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    meta_model = (options.metadata or {}).get("model") if options else None
    if isinstance(meta_model, str) and meta_model.strip():
        return meta_model.strip()
    return "unknown"


def extract_tokens(raw: Any) -> Tuple[int, int]:
    """Extract (input_tokens, output_tokens) from a LangChain AIMessage result."""
    if raw is None:
        return 0, 0

    # langchain_core normalises this on AIMessage as `usage_metadata`.
    usage = getattr(raw, "usage_metadata", None)
    if isinstance(usage, dict):
        in_tok = int(usage.get("input_tokens") or 0)
        out_tok = int(usage.get("output_tokens") or 0)
        if in_tok or out_tok:
            return in_tok, out_tok

    metadata = getattr(raw, "response_metadata", None) or {}
    if isinstance(metadata, dict):
        # OpenAI-compatible (Groq, OpenAI, DeepSeek)
        token_usage = metadata.get("token_usage")
        if isinstance(token_usage, dict):
            in_tok = int(token_usage.get("prompt_tokens") or 0)
            out_tok = int(token_usage.get("completion_tokens") or 0)
            if in_tok or out_tok:
                return in_tok, out_tok

        # Gemini variants
        usage_md = metadata.get("usage_metadata")
        if isinstance(usage_md, dict):
            in_tok = int(
                usage_md.get("input_tokens")
                or usage_md.get("prompt_token_count")
                or 0
            )
            out_tok = int(
                usage_md.get("output_tokens")
                or usage_md.get("candidates_token_count")
                or 0
            )
            if in_tok or out_tok:
                return in_tok, out_tok

    return 0, 0
