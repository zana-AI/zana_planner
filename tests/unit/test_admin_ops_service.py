import logging
from urllib.parse import parse_qs, urlparse

from services.admin_ops_service import (
    ErrorAlertRateLimiter,
    build_github_issue_url,
    error_fingerprint,
    redact_sensitive_text,
)


def test_redact_sensitive_text_masks_common_secret_shapes(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    monkeypatch.setenv("DATABASE_URL_STAGING", "postgresql://user:pass@example/db")

    raw = (
        "token=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ "
        "Authorization: Bearer abcdefghijklmnop "
        "url=https://example.com/path?session=abc123&ok=1 "
        "db=postgresql://user:pass@example/db "
        "github=ghp_abcdefghijklmnopqrstuvwxyz123456"
    )

    redacted = redact_sensitive_text(raw)

    assert "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in redacted
    assert "abcdefghijklmnop" not in redacted
    assert "session=abc123" not in redacted
    assert "postgresql://user:pass@example/db" not in redacted
    assert "ghp_abcdefghijklmnopqrstuvwxyz123456" not in redacted
    assert "[redacted]" in redacted


def test_error_alert_rate_limiter_suppresses_duplicate_within_window():
    limiter = ErrorAlertRateLimiter(window_seconds=60)

    first = limiter.check("abc", now=100)
    second = limiter.check("abc", now=120)
    third = limiter.check("abc", now=161)

    assert first.should_send is True
    assert second.should_send is False
    assert second.suppressed_count == 1
    assert third.should_send is True
    assert third.suppressed_count == 1


def test_error_fingerprint_is_stable_for_normalized_messages():
    record_one = logging.LogRecord(
        name="webapp.routers.auth",
        level=logging.ERROR,
        pathname="/app/tm_bot/webapp/routers/auth.py",
        lineno=97,
        msg="Failed for user 123 at 2026-05-21T23:10:48Z",
        args=(),
        exc_info=None,
    )
    record_two = logging.LogRecord(
        name="webapp.routers.auth",
        level=logging.ERROR,
        pathname="/app/tm_bot/webapp/routers/auth.py",
        lineno=98,
        msg="Failed for user 456 at 2026-05-22T01:10:48Z",
        args=(),
        exc_info=None,
    )

    assert error_fingerprint(record_one) == error_fingerprint(record_two)


def test_build_github_issue_url_prefills_issue_without_token(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ")

    issue_url = build_github_issue_url(
        repository="zana-AI/zana_planner",
        title="System error abc123",
        body="Failure token=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        labels=["bug", "admin-error"],
    )

    parsed = urlparse(issue_url)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "github.com"
    assert parsed.path == "/zana-AI/zana_planner/issues/new"
    assert query["title"] == ["System error abc123"]
    assert query["labels"] == ["bug,admin-error"]
    assert "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in query["body"][0]
    assert "[redacted]" in query["body"][0]
