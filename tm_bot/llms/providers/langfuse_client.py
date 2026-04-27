"""Langfuse tracing for Xaana LLM calls.

Lazy singleton + fire-and-forget `trace_generation()`. All errors are
swallowed so a Langfuse outage never crashes the bot, mirroring the
swallow-all pattern in `providers.telemetry.record_usage_safely`.

Configuration via env (any one missing -> tracing disabled silently):
    LANGFUSE_HOST           e.g. https://langfuse.xaana.club  or cloud.langfuse.com
    LANGFUSE_PUBLIC_KEY     pk-lf-...
    LANGFUSE_SECRET_KEY     sk-lf-...

Optional:
    LANGFUSE_REDACT_PII     "true"|"false" (default "true"). When true, strips
                            email addresses, URLs, and phone-like number runs
                            from message inputs/outputs before sending.

Per-message context (Telegram user_id / chat_id / message_id) is read from
contextvars set by bot handlers via `set_bot_context()`. If unset, traces
are still sent, just ungrouped.
"""

from __future__ import annotations

import contextvars
import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Sequence

_logger = logging.getLogger(__name__)


# --- Per-message context ----------------------------------------------------

_ctx_user_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "xaana_lf_user_id", default=None,
)
_ctx_chat_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "xaana_lf_chat_id", default=None,
)
_ctx_message_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "xaana_lf_message_id", default=None,
)


def set_bot_context(
    *,
    user_id: Optional[Any] = None,
    chat_id: Optional[Any] = None,
    message_id: Optional[Any] = None,
) -> Dict[str, contextvars.Token]:
    """Set per-message context. Caller must pass the returned dict to
    `reset_bot_context()` when the message is fully processed."""
    tokens: Dict[str, contextvars.Token] = {}
    if user_id is not None:
        tokens["user_id"] = _ctx_user_id.set(str(user_id))
    if chat_id is not None:
        tokens["chat_id"] = _ctx_chat_id.set(str(chat_id))
    if message_id is not None:
        tokens["message_id"] = _ctx_message_id.set(str(message_id))
    return tokens


def reset_bot_context(tokens: Dict[str, contextvars.Token]) -> None:
    if not tokens:
        return
    if "user_id" in tokens:
        _ctx_user_id.reset(tokens["user_id"])
    if "chat_id" in tokens:
        _ctx_chat_id.reset(tokens["chat_id"])
    if "message_id" in tokens:
        _ctx_message_id.reset(tokens["message_id"])


# --- Lazy singleton ---------------------------------------------------------

_client_lock = threading.Lock()
_client_loaded = False
_client: Any = None


def _get_client() -> Any:
    global _client_loaded, _client
    if _client_loaded:
        return _client
    with _client_lock:
        if _client_loaded:
            return _client
        _client_loaded = True

        public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
        secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
        host = os.environ.get("LANGFUSE_HOST", "").strip()
        if not (public_key and secret_key and host):
            _logger.info(
                "Langfuse not configured (missing LANGFUSE_HOST/PUBLIC_KEY/SECRET_KEY); "
                "tracing disabled"
            )
            _client = None
            return None
        try:
            from langfuse import Langfuse  # type: ignore
        except Exception as exc:  # pragma: no cover
            _logger.warning("langfuse SDK not importable (%s); tracing disabled", exc)
            _client = None
            return None
        try:
            _client = Langfuse(
                host=host,
                public_key=public_key,
                secret_key=secret_key,
            )
            _logger.info("Langfuse client initialised (host=%s)", host)
        except Exception as exc:  # pragma: no cover
            _logger.warning("Failed to construct Langfuse client (%s); tracing disabled", exc)
            _client = None
        return _client


# --- PII redaction ----------------------------------------------------------

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_URL_RE = re.compile(r"https?://\S+")
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}(?!\d)"
)


def _redact(text: str) -> str:
    if not text:
        return text
    text = _EMAIL_RE.sub("[email]", text)
    text = _URL_RE.sub("[url]", text)
    text = _PHONE_RE.sub("[phone]", text)
    return text


def _redaction_enabled() -> bool:
    raw = os.environ.get("LANGFUSE_REDACT_PII", "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _render_message(m: Any, redact: bool) -> Dict[str, Any]:
    role = getattr(m, "type", None) or getattr(m, "role", None) or "message"
    content = getattr(m, "content", None)
    if isinstance(content, str):
        content = _redact(content) if redact else content
    elif isinstance(content, list):
        rendered: List[Any] = []
        for part in content:
            if isinstance(part, dict) and "text" in part and redact:
                rendered.append({**part, "text": _redact(part.get("text") or "")})
            else:
                rendered.append(part)
        content = rendered
    return {"role": role, "content": content}


# --- Background dispatcher --------------------------------------------------

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="langfuse-trace")


def trace_generation(
    *,
    provider: str,
    model_name: str,
    role: Optional[str],
    messages_in: Sequence[Any],
    output_text: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    success: bool,
    error_type: Optional[str],
) -> None:
    """Fire-and-forget. Never raises."""
    try:
        _executor.submit(
            _send_trace,
            provider=provider,
            model_name=model_name,
            role=role,
            messages_in=list(messages_in),
            output_text=output_text or "",
            input_tokens=int(input_tokens or 0),
            output_tokens=int(output_tokens or 0),
            latency_ms=int(latency_ms or 0),
            success=bool(success),
            error_type=error_type,
            user_id=_ctx_user_id.get(),
            chat_id=_ctx_chat_id.get(),
            message_id=_ctx_message_id.get(),
        )
    except Exception as exc:  # pragma: no cover
        _logger.debug("trace_generation submit failed (%s); ignoring", exc)


def flag_trace(
    *,
    trace_id: str,
    flagged_by: Optional[Any] = None,
) -> Dict[str, Any]:
    """Synchronously flag a trace for human review by writing a Langfuse
    score (`name="needs_review"`, `value=1`).

    Returns ``{"ok": bool, "message": str}``. Never raises — admin endpoint
    surfaces ``ok=False`` as a 503.
    """
    client = _get_client()
    if client is None:
        return {"ok": False, "message": "Langfuse not configured"}
    try:
        client.score(
            trace_id=trace_id,
            name="needs_review",
            value=1,
            comment=(
                f"flagged_by_admin={flagged_by}" if flagged_by is not None else None
            ),
        )
        return {"ok": True, "message": "flagged"}
    except Exception as exc:
        _logger.warning("Langfuse flag_trace failed (%s)", exc)
        return {"ok": False, "message": f"langfuse score failed: {exc}"}


def _send_trace(
    *,
    provider: str,
    model_name: str,
    role: Optional[str],
    messages_in: List[Any],
    output_text: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    success: bool,
    error_type: Optional[str],
    user_id: Optional[str],
    chat_id: Optional[str],
    message_id: Optional[str],
) -> None:
    try:
        client = _get_client()
        if client is None:
            return
        redact = _redaction_enabled()
        rendered_input = [_render_message(m, redact) for m in messages_in]
        rendered_output = _redact(output_text) if redact else output_text

        trace = client.trace(
            name=f"xaana.{role or 'llm'}",
            user_id=user_id,
            session_id=chat_id,
            metadata={
                "message_id": message_id,
                "provider": provider,
                "redacted": redact,
            },
        )
        trace.generation(
            name=role or "llm",
            model=model_name,
            input=rendered_input,
            output=rendered_output,
            usage={
                "input": input_tokens,
                "output": output_tokens,
                "total": input_tokens + output_tokens,
            },
            metadata={"latency_ms": latency_ms, "provider": provider},
            level="ERROR" if not success else "DEFAULT",
            status_message=error_type,
        )
    except Exception as exc:  # pragma: no cover
        _logger.debug("Langfuse send failed (%s); ignoring", exc)
