"""Best-effort LLM usage telemetry shared by provider wrappers and raw clients."""
from __future__ import annotations

import logging
from typing import Optional

_logger = logging.getLogger(__name__)


def record_usage_safely(
    *,
    provider: str,
    model_name: str,
    role: Optional[str],
    input_tokens: int,
    output_tokens: int,
    latency_ms: Optional[int] = None,
    success: bool = True,
    error_type: Optional[str] = None,
) -> None:
    """Log one LLM call without ever affecting the request path."""
    try:
        from repositories.llm_usage_repo import log_usage  # local import to avoid cycles
    except Exception as exc:
        _logger.debug("llm_usage_repo unavailable (%s); skipping telemetry", exc)
        return

    try:
        log_usage(
            provider=provider,
            model_name=model_name,
            role=role,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            success=success,
            error_type=error_type,
        )
    except Exception as exc:  # pragma: no cover
        _logger.debug("log_usage failed (%s); ignoring", exc)
