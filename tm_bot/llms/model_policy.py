from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
import re
from typing import Any, Dict, Iterable, Optional, Tuple

from langchain_core.messages import BaseMessage

DEFAULT_BLOCK_SECONDS = 30.0


@dataclass(frozen=True)
class ModelCapabilities:
    context_window_tokens: int
    max_output_tokens: int
    tokenizer_family: str


@dataclass
class ModelQuotaState:
    remaining_requests: Optional[int] = None
    remaining_tokens: Optional[int] = None
    limit_requests: Optional[int] = None
    limit_tokens: Optional[int] = None
    reset_requests_at: Optional[datetime] = None
    reset_tokens_at: Optional[datetime] = None
    blocked_until: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    last_error: Optional[str] = None


# Hardcoded model capabilities (doc-based baseline, can be revised independently).
MODEL_CAPABILITIES: Dict[str, ModelCapabilities] = {
    "gemini-2.5-flash": ModelCapabilities(
        context_window_tokens=1_048_576,
        max_output_tokens=65_536,
        tokenizer_family="gemini_approx",
    ),
    "gemini-2.5-flash-lite": ModelCapabilities(
        context_window_tokens=1_048_576,
        max_output_tokens=65_536,
        tokenizer_family="gemini_approx",
    ),
    "gpt-4o-mini": ModelCapabilities(
        context_window_tokens=128_000,
        max_output_tokens=16_384,
        tokenizer_family="o200k_base",
    ),
    "deepseek-chat": ModelCapabilities(
        context_window_tokens=64_000,
        max_output_tokens=8_192,
        tokenizer_family="deepseek_approx",
    ),
    "openai/gpt-oss-20b": ModelCapabilities(
        context_window_tokens=131_072,
        max_output_tokens=16_384,
        tokenizer_family="o200k_base",
    ),
    "openai/gpt-oss-120b": ModelCapabilities(
        context_window_tokens=131_072,
        max_output_tokens=16_384,
        tokenizer_family="o200k_base",
    ),
    "llama-3.3-70b-versatile": ModelCapabilities(
        context_window_tokens=131_072,
        max_output_tokens=8_192,
        tokenizer_family="llama_approx",
    ),
}


# Announced Groq limits (as of 2026-02-23 from provider docs).
GROQ_RATE_LIMITS_BY_PLAN: Dict[str, Dict[str, Dict[str, Optional[int]]]] = {
    "free": {
        "openai/gpt-oss-20b": {
            "rpm": 30,
            "rpd": 1_000,
            "tpm": 8_000,
            "tpd": 200_000,
        },
        "llama-3.3-70b-versatile": {
            "rpm": 30,
            "rpd": 1_000,
            "tpm": 12_000,
            "tpd": 100_000,
        },
    },
    "developer": {
        "openai/gpt-oss-20b": {
            "rpm": 1_000,
            "rpd": 500_000,
            "tpm": 250_000,
            "tpd": None,
        },
        "llama-3.3-70b-versatile": {
            "rpm": 1_000,
            "rpd": 500_000,
            "tpm": 300_000,
            "tpd": None,
        },
    },
}

_quota_lock = RLock()
_quota_states: Dict[Tuple[str, str], ModelQuotaState] = {}
_encoding_cache: Dict[str, Any] = {}

_DURATION_RE = re.compile(r"(?:(?P<h>\d+(?:\.\d+)?)h)?(?:(?P<m>\d+(?:\.\d+)?)m)?(?:(?P<s>\d+(?:\.\d+)?)s)?$")
_TOKEN_UNIT_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kKmM]?)\s*$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _key(provider: str, model_id: str) -> Tuple[str, str]:
    return (str(provider or "").strip().lower(), str(model_id or "").strip())


def _state(provider: str, model_id: str) -> ModelQuotaState:
    k = _key(provider, model_id)
    with _quota_lock:
        existing = _quota_states.get(k)
        if existing is None:
            existing = ModelQuotaState()
            _quota_states[k] = existing
        return existing


def _parse_compact_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    match = _TOKEN_UNIT_RE.match(text)
    if not match:
        return None
    amount = float(match.group(1))
    suffix = (match.group(2) or "").lower()
    multiplier = 1
    if suffix == "k":
        multiplier = 1_000
    elif suffix == "m":
        multiplier = 1_000_000
    return int(amount * multiplier)


def parse_reset_duration_seconds(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value < 0:
            return None
        return float(value)

    text = str(value).strip().lower()
    if not text:
        return None

    if text.endswith("ms"):
        try:
            return max(0.0, float(text[:-2]) / 1000.0)
        except ValueError:
            return None

    if text.replace(".", "", 1).isdigit():
        return max(0.0, float(text))

    match = _DURATION_RE.match(text)
    if not match:
        return None

    hours = float(match.group("h") or 0.0)
    minutes = float(match.group("m") or 0.0)
    seconds = float(match.group("s") or 0.0)
    total = hours * 3600.0 + minutes * 60.0 + seconds
    return max(0.0, total)


def _flatten_headers(metadata: Any) -> Dict[str, str]:
    if not isinstance(metadata, dict):
        return {}

    raw = None
    for key in ("headers", "response_headers", "http_headers"):
        if key in metadata and metadata.get(key) is not None:
            raw = metadata.get(key)
            break

    if raw is None:
        return {}

    items = None
    if isinstance(raw, dict):
        items = raw.items()
    elif hasattr(raw, "items"):
        try:
            items = raw.items()
        except Exception:
            items = None
    if items is None:
        return {}

    out: Dict[str, str] = {}
    for key, value in items:
        k = str(key or "").strip().lower()
        if not k:
            continue
        if isinstance(value, list) and value:
            value = value[0]
        out[k] = str(value).strip()
    return out


def get_model_capabilities(model_id: str) -> Optional[ModelCapabilities]:
    return MODEL_CAPABILITIES.get(str(model_id or "").strip())


def _fallback_token_estimate(text: str) -> int:
    if not text:
        return 0
    # Pragmatic fallback for mixed providers when tokenizer isn't available.
    return max(1, int(len(text) / 4))


def _get_tiktoken_encoding(encoding_name: str):
    if encoding_name in _encoding_cache:
        return _encoding_cache[encoding_name]
    try:
        import tiktoken  # type: ignore

        enc = tiktoken.get_encoding(encoding_name)
    except Exception:
        enc = None
    _encoding_cache[encoding_name] = enc
    return enc


def estimate_tokens(text: str, model_id: str | None = None) -> int:
    content = (text or "").strip()
    if not content:
        return 0

    capabilities = get_model_capabilities(model_id or "") if model_id else None
    tokenizer_family = (capabilities.tokenizer_family if capabilities else "o200k_base").strip().lower()

    if tokenizer_family in {"o200k_base", "cl100k_base", "p50k_base"}:
        enc = _get_tiktoken_encoding(tokenizer_family)
        if enc is not None:
            try:
                return len(enc.encode(content))
            except Exception:
                return _fallback_token_estimate(content)

    return _fallback_token_estimate(content)


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text
    return str(content)


def estimate_messages_tokens(messages: Iterable[BaseMessage] | Iterable[str], model_id: str | None = None) -> int:
    total = 0
    for message in messages or []:
        if isinstance(message, str):
            text = message
        elif isinstance(message, BaseMessage):
            text = _content_to_text(getattr(message, "content", None))
        else:
            text = _content_to_text(getattr(message, "content", message))
        total += estimate_tokens(text, model_id=model_id)
    return total


def update_from_response_metadata(provider: str, model_id: str, response_metadata: Any) -> None:
    headers = _flatten_headers(response_metadata)
    if not headers:
        return

    now = _utc_now()
    state = _state(provider, model_id)
    with _quota_lock:
        state.last_seen_at = now

        state.limit_requests = _parse_compact_int(
            headers.get("x-ratelimit-limit-requests")
        ) or state.limit_requests
        state.limit_tokens = _parse_compact_int(
            headers.get("x-ratelimit-limit-tokens")
        ) or state.limit_tokens
        state.remaining_requests = _parse_compact_int(
            headers.get("x-ratelimit-remaining-requests")
        )
        state.remaining_tokens = _parse_compact_int(
            headers.get("x-ratelimit-remaining-tokens")
        )

        reset_requests = parse_reset_duration_seconds(headers.get("x-ratelimit-reset-requests"))
        reset_tokens = parse_reset_duration_seconds(headers.get("x-ratelimit-reset-tokens"))
        if reset_requests is not None:
            state.reset_requests_at = now + timedelta(seconds=reset_requests)
        if reset_tokens is not None:
            state.reset_tokens_at = now + timedelta(seconds=reset_tokens)

        candidate_block_until = None
        if state.remaining_requests is not None and state.remaining_requests <= 0:
            candidate_block_until = state.reset_requests_at
        if state.remaining_tokens is not None and state.remaining_tokens <= 0:
            token_block_until = state.reset_tokens_at
            if token_block_until is not None:
                if candidate_block_until is None or token_block_until > candidate_block_until:
                    candidate_block_until = token_block_until
        if candidate_block_until is not None:
            state.blocked_until = candidate_block_until


def mark_rate_limited(
    provider: str,
    model_id: str,
    retry_after_s: float | None = None,
    reset_hint: str | None = None,
) -> None:
    now = _utc_now()
    delay_seconds = retry_after_s if retry_after_s and retry_after_s > 0 else None
    if delay_seconds is None:
        delay_seconds = parse_reset_duration_seconds(reset_hint)
    if delay_seconds is None or delay_seconds <= 0:
        delay_seconds = DEFAULT_BLOCK_SECONDS

    blocked_until = now + timedelta(seconds=float(delay_seconds))
    state = _state(provider, model_id)
    with _quota_lock:
        state.blocked_until = blocked_until
        state.last_seen_at = now
        state.last_error = "rate_limited"


def is_blocked(provider: str, model_id: str, now: datetime | None = None) -> bool:
    current = now or _utc_now()
    k = _key(provider, model_id)
    with _quota_lock:
        state = _quota_states.get(k)
        if state is None or state.blocked_until is None:
            return False
        if current >= state.blocked_until:
            state.blocked_until = None
            return False
        return True


def pick_first_available(provider: str, candidate_models: list[str]) -> str | None:
    for model_id in candidate_models or []:
        if not model_id:
            continue
        if not is_blocked(provider, model_id):
            return model_id
    return None


def snapshot(provider: str, model_id: str) -> Dict[str, Any]:
    state = _state(provider, model_id)
    with _quota_lock:
        payload = asdict(state)
    for field in (
        "reset_requests_at",
        "reset_tokens_at",
        "blocked_until",
        "last_seen_at",
    ):
        value = payload.get(field)
        if isinstance(value, datetime):
            payload[field] = value.isoformat()
    return payload


def get_announced_rate_limit(provider: str, model_id: str, plan_tier: str = "free") -> Dict[str, Optional[int]]:
    provider_key = str(provider or "").strip().lower()
    if provider_key != "groq":
        return {}
    tier = (plan_tier or "free").strip().lower()
    if tier not in GROQ_RATE_LIMITS_BY_PLAN:
        tier = "free"
    return dict(GROQ_RATE_LIMITS_BY_PLAN.get(tier, {}).get(str(model_id or "").strip(), {}))
