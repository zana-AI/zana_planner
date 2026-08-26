"""
Translation for user-facing bot text.

Runs on the same Groq stack as the rest of the LLM path. It used to call
Google Cloud Translation, which stopped working when the project moved off GCP
— every non-English message then logged an ERROR and silently fell back to
English. There is deliberately **no Google dependency left in this module**;
adding one back would reintroduce a runtime dependency on credentials the
project no longer has.

Failure is always soft: callers get the original English text, never an
exception. The unreachable-service case is logged once per process rather than
once per message, so a misconfiguration is visible without flooding the log.
"""

import os
import threading
import time
from typing import Dict, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

# Process-lifetime cache. Most traffic through here is a small set of fixed UI
# strings ("Open App…", nightly reminders), so this collapses to a handful of
# calls per language after warm-up.
_translation_cache: Dict[str, str] = {}
_cache_lock = threading.Lock()

_MODEL = "openai/gpt-oss-20b"
_FALLBACK_MODEL = "openai/gpt-oss-120b"
_GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Only warn once per process that translation is unavailable — otherwise a
# missing key produces one log line per outgoing message.
_unavailable_warned = False

_LANGUAGE_NAMES = {
    "en": "English",
    "fa": "Persian (Farsi)",
    "fr": "French",
}

_SYSTEM_PROMPT = (
    "You are a translation engine inside a habit-tracking Telegram bot.\n"
    "Translate the user's text from {source} to {target}.\n"
    "\n"
    "Rules:\n"
    "- Output ONLY the translation. No preamble, no quotes, no explanation.\n"
    "- Preserve every emoji, URL, @mention and Markdown marker (*, _, `, **) "
    "exactly where they are.\n"
    "- Preserve placeholders like {{name}} or __PLACEHOLDER_0__ verbatim — never "
    "translate or reorder their contents.\n"
    "- Keep the tone short, warm and direct, as in the original.\n"
    "- If the text is already in {target}, return it unchanged."
)


def _language_name(code: str) -> str:
    return _LANGUAGE_NAMES.get((code or "").lower().strip(), code)


def _warn_unavailable(reason: str) -> None:
    global _unavailable_warned
    if not _unavailable_warned:
        _unavailable_warned = True
        logger.warning(
            "Translation unavailable (%s) — sending English text as-is. "
            "This is logged once per process.",
            reason,
        )


def translate_text(text: str, target_lang: str, source_lang: str = "en") -> str:
    """
    Translate `text` into `target_lang`, falling back to the original on any
    failure. Cached per (source, target, text).
    """
    if not text or not text.strip() or target_lang == source_lang:
        return text

    cache_key = f"{source_lang}:{target_lang}:{text}"
    with _cache_lock:
        cached = _translation_cache.get(cache_key)
    if cached is not None:
        return cached

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        _warn_unavailable("GROQ_API_KEY is not set")
        return text

    system_prompt = _SYSTEM_PROMPT.format(
        source=_language_name(source_lang),
        target=_language_name(target_lang),
    )

    translated = _call_groq(api_key, system_prompt, text)
    if translated is None:
        return text

    with _cache_lock:
        _translation_cache[cache_key] = translated
    return translated


def _call_groq(api_key: str, system_prompt: str, text: str) -> Optional[str]:
    """One translation call, primary model then fallback. None if both fail."""
    from llms.providers.telemetry import record_usage_safely
    from llms.providers.usage import extract_tokens

    # Translations are roughly length-preserving; give the model room for a
    # longer target script (Persian runs longer than English) plus the hidden
    # reasoning tokens gpt-oss models emit before their answer.
    max_tokens = min(2048, max(256, len(text) * 2))

    for model in (_MODEL, _FALLBACK_MODEL):
        start = time.perf_counter()
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=_GROQ_BASE_URL)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                max_tokens=max_tokens,
                temperature=0.0,
                # gpt-oss-* spend part of the budget on hidden chain-of-thought;
                # "low" keeps enough of it for the actual translation. Same
                # reason as llms/group_router.py.
                reasoning_effort="low",
            )
            output = (response.choices[0].message.content or "").strip()
            latency_ms = int((time.perf_counter() - start) * 1000)
            input_tokens, output_tokens = extract_tokens(response)
            record_usage_safely(
                provider="groq",
                model_name=model,
                role="translator",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                success=bool(output),
                error_type=None if output else "empty_response",
            )
            if output:
                return output
            logger.warning("translate: %s returned an empty response", model)
        except Exception as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            record_usage_safely(
                provider="groq",
                model_name=model,
                role="translator",
                input_tokens=0,
                output_tokens=0,
                latency_ms=latency_ms,
                success=False,
                error_type=type(exc).__name__,
            )
            logger.warning("translate: %s failed: %s", model, exc)

    _warn_unavailable("all Groq models failed")
    return None


def clear_translation_cache() -> None:
    """Clear the translation cache."""
    with _cache_lock:
        _translation_cache.clear()
    logger.info("Translation cache cleared")


def get_cache_size() -> int:
    """Get the current size of the translation cache."""
    with _cache_lock:
        return len(_translation_cache)
