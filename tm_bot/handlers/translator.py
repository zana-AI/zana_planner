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

import json
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

_LEARNING_TERM_PROMPT = (
    "You are a concise bilingual dictionary for a language learner.\n"
    "Translate the term from {source} to {target} using the sentence context to "
    "choose the intended sense.\n"
    "Output ONLY the shortest natural translation of the term. No labels, quotes, "
    "romanization, definition, alternatives, or explanation."
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


def translate_learning_term(
    term: str,
    context: str,
    target_lang: str,
    source_lang: str = "fr",
) -> Optional[str]:
    """Translate one learning term in context, returning None on failure.

    Unlike user-facing UI translation, a failed dictionary lookup must not
    masquerade as a valid answer by returning the source word. One compact
    model call is enough here; callers can show a soft unavailable state.
    """
    clean_term = " ".join((term or "").strip().split())
    clean_context = " ".join((context or "").strip().split())[:500]
    source = (source_lang or "fr").lower().strip()
    target = (target_lang or "en").lower().strip()
    if not clean_term or source == target:
        return clean_term or None

    cache_key = f"learning:{source}:{target}:{clean_term}:{clean_context}"
    with _cache_lock:
        cached = _translation_cache.get(cache_key)
    if cached is not None:
        return cached

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        _warn_unavailable("GROQ_API_KEY is not set")
        return None

    system_prompt = _LEARNING_TERM_PROMPT.format(
        source=_language_name(source),
        target=_language_name(target),
    )
    user_text = f"Term: {clean_term}\nContext: {clean_context or clean_term}"
    translated = _call_groq(
        api_key,
        system_prompt,
        user_text,
        models=(_MODEL,),
        max_tokens=96,
    )
    if translated:
        with _cache_lock:
            _translation_cache[cache_key] = translated
    return translated


_CARD_PROMPT = (
    "You write flashcards for a {source} learner whose own language is {target}.\n"
    "Given a term the learner tapped and the passage it appeared in, reply with ONE "
    "JSON object and nothing else, with these keys in this order:\n"
    '  "sentence": the one sentence from the passage that contains the term, copied '
    "exactly (automatic subtitles may lack punctuation; keep the words as they are).\n"
    '  "sentence_translation": that sentence translated naturally into {target}.\n'
    '  "headword": what the learner should memorise. Decide first whether the term is '
    "part of a multi-word expression in this sentence: an idiom, a fixed locution, or "
    "a verb that only has this meaning with its preposition or object. If it is, give "
    "the WHOLE expression in dictionary form (verb in the infinitive, pronominal verbs "
    "with se). Example: the term \"compte\" in \"il s'est rendu compte\" gives "
    "\"se rendre compte\". An expression keeps its verb: never return a fragment "
    "such as a preposition plus a noun without the verb it belongs to. Otherwise "
    "give the single word in dictionary form, with the "
    "article for nouns (le/la/l').\n"
    '  "grammar": a short {source} label such as "n.f.", "n.m.", "v.", "adj.", "adv.", '
    '"loc. verbale", "expr.".\n'
    '  "translation": the meaning of the headword as used here, in {target}, a few '
    "words at most.\n"
    '  "usage_note": one short line in {target} on register or usage, or "".\n'
    "No other keys, no markdown, no commentary."
)
_CARD_KEYS = ("headword", "grammar", "translation", "sentence", "sentence_translation", "usage_note")
# The small model returns clean JSON but misses idioms ("brèche" alone for
# "battre en brèche"), which is most of what this call is for. The card is
# built once, at save time, so the larger model's extra second is affordable.
_CARD_MODELS = ("openai/gpt-oss-120b", _MODEL)


def enrich_learning_card(
    term: str,
    passage: str,
    target_lang: str,
    source_lang: str = "fr",
) -> Optional[dict]:
    """Build the learning fields of a flashcard in one model call.

    The in-player lookup is deliberately a bare gloss for speed. At save time
    there is time for one structured call that recovers what a gloss loses:
    the dictionary form, the idiom a word belongs to ("brèche" in "battre en
    brèche"), and a translation of the whole sentence. Returns None on any
    failure so the caller saves the card exactly as it would have without it.
    """
    clean_term = " ".join((term or "").strip().split())
    clean_passage = " ".join((passage or "").strip().split())[:900]
    source = (source_lang or "fr").lower().strip()
    target = (target_lang or "en").lower().strip()
    if not clean_term or source == target:
        return None

    cache_key = f"card:{source}:{target}:{clean_term}:{clean_passage}"
    with _cache_lock:
        cached = _translation_cache.get(cache_key)
    if isinstance(cached, dict):
        return cached

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        _warn_unavailable("GROQ_API_KEY is not set")
        return None

    raw = _call_groq(
        api_key,
        _CARD_PROMPT.format(source=_language_name(source), target=_language_name(target)),
        f"Term: {clean_term}\nPassage: {clean_passage or clean_term}",
        models=_CARD_MODELS,
        max_tokens=900,
    )
    card = _parse_card_json(raw)
    if card:
        with _cache_lock:
            _translation_cache[cache_key] = card
    return card


def _parse_card_json(raw: Optional[str]) -> Optional[dict]:
    """Keep only known, non-empty string fields; None if nothing usable."""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):] if "{" in text else text
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except ValueError:
        logger.warning("enrich_learning_card: model returned invalid JSON")
        return None
    if not isinstance(data, dict):
        return None
    card = {
        key: " ".join(str(data[key]).split())[:400]
        for key in _CARD_KEYS
        if isinstance(data.get(key), str) and data[key].strip()
    }
    return card if card.get("headword") and card.get("translation") else None


def _call_groq(
    api_key: str,
    system_prompt: str,
    text: str,
    *,
    models: tuple[str, ...] = (_MODEL, _FALLBACK_MODEL),
    max_tokens: Optional[int] = None,
) -> Optional[str]:
    """One translation call, primary model then fallback. None if both fail."""
    from llms.providers.telemetry import record_usage_safely
    from llms.providers.usage import extract_tokens

    # Translations are roughly length-preserving; give the model room for a
    # longer target script (Persian runs longer than English) plus the hidden
    # reasoning tokens gpt-oss models emit before their answer.
    resolved_max_tokens = max_tokens or min(2048, max(256, len(text) * 2))

    for model in models:
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
                max_tokens=resolved_max_tokens,
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
