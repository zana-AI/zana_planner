import os
import sys
from datetime import datetime, timedelta, timezone

from langchain_core.messages import HumanMessage

TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.append(TM_BOT_DIR)

from llms.model_policy import (  # noqa: E402
    estimate_messages_tokens,
    estimate_tokens,
    is_blocked,
    mark_rate_limited,
    parse_reset_duration_seconds,
    pick_first_available,
    snapshot,
    update_from_response_metadata,
)


def test_estimate_tokens_returns_positive_for_known_model():
    text = "This is a token estimation sample."
    assert estimate_tokens(text, model_id="openai/gpt-oss-20b") > 0


def test_estimate_messages_tokens_with_messages_and_strings():
    messages = [
        HumanMessage(content="hello world"),
        "second string payload",
    ]
    assert estimate_messages_tokens(messages, model_id="gpt-4o-mini") > 0


def test_parse_reset_duration_seconds_supports_compound_values():
    assert parse_reset_duration_seconds("7.66s") == 7.66
    assert parse_reset_duration_seconds("2m59.56s") == 179.56
    assert parse_reset_duration_seconds("1h") == 3600.0
    assert parse_reset_duration_seconds("120ms") == 0.12


def test_update_from_response_metadata_populates_quota_state():
    provider = "groq"
    model = "openai/gpt-oss-20b"
    metadata = {
        "headers": {
            "x-ratelimit-limit-requests": "30",
            "x-ratelimit-limit-tokens": "8000",
            "x-ratelimit-remaining-requests": "12",
            "x-ratelimit-remaining-tokens": "4200",
            "x-ratelimit-reset-requests": "8s",
            "x-ratelimit-reset-tokens": "11s",
        }
    }
    update_from_response_metadata(provider, model, metadata)
    snap = snapshot(provider, model)

    assert snap["limit_requests"] == 30
    assert snap["limit_tokens"] == 8000
    assert snap["remaining_requests"] == 12
    assert snap["remaining_tokens"] == 4200
    assert snap["reset_requests_at"] is not None
    assert snap["reset_tokens_at"] is not None


def test_mark_rate_limited_sets_block_and_pick_first_available_skips_it():
    provider = "groq"
    blocked_model = "unit-test-blocked-groq-model"
    fallback_model = "llama-3.3-70b-versatile"

    mark_rate_limited(provider, blocked_model, retry_after_s=45)
    assert is_blocked(provider, blocked_model) is True

    selected = pick_first_available(provider, [blocked_model, fallback_model])
    assert selected == fallback_model


def test_is_blocked_expires_when_now_moves_past_block_window():
    provider = "groq"
    model = "unit-test-expiring-groq-model"
    mark_rate_limited(provider, model, retry_after_s=5)

    future = datetime.now(timezone.utc) + timedelta(seconds=10)
    assert is_blocked(provider, model, now=future) is False
