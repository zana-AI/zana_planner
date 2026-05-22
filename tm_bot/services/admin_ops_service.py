"""Admin operations helpers for error triage and deploy approvals."""

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from logging import LogRecord
from types import TracebackType
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


REDACTED = "[redacted]"
DEFAULT_DEDUPE_SECONDS = 15 * 60

_SECRET_ENV_MARKERS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASS",
    "KEY",
    "CREDENTIAL",
    "DATABASE_URL",
    "DB_URL",
    "DSN",
    "COOKIE",
    "SESSION",
)
_SENSITIVE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "auth",
    "authorization",
    "bot_token",
    "code",
    "credential",
    "hash",
    "initdata",
    "key",
    "password",
    "secret",
    "session",
    "session_token",
    "signature",
    "token",
}


@dataclass
class RateLimitDecision:
    """Result of an alert duplicate check."""

    should_send: bool
    suppressed_count: int = 0


class ErrorAlertRateLimiter:
    """In-memory duplicate suppressor keyed by stable error fingerprint."""

    def __init__(self, window_seconds: int = DEFAULT_DEDUPE_SECONDS) -> None:
        self.window_seconds = max(0, int(window_seconds))
        self._state: dict[str, dict[str, float | int]] = {}

    def check(self, fingerprint: str, now: Optional[float] = None) -> RateLimitDecision:
        if not fingerprint or self.window_seconds <= 0:
            return RateLimitDecision(should_send=True)

        current = time.time() if now is None else now
        state = self._state.get(fingerprint)
        if not state:
            self._state[fingerprint] = {"last_sent": current, "suppressed": 0}
            return RateLimitDecision(should_send=True)

        last_sent = float(state.get("last_sent") or 0)
        if current - last_sent < self.window_seconds:
            suppressed = int(state.get("suppressed") or 0) + 1
            state["suppressed"] = suppressed
            return RateLimitDecision(should_send=False, suppressed_count=suppressed)

        suppressed = int(state.get("suppressed") or 0)
        self._state[fingerprint] = {"last_sent": current, "suppressed": 0}
        return RateLimitDecision(should_send=True, suppressed_count=suppressed)


def _env_secret_values() -> list[str]:
    values: list[str] = []
    for key, value in os.environ.items():
        if not value or len(value) < 8:
            continue
        upper_key = key.upper()
        if any(marker in upper_key for marker in _SECRET_ENV_MARKERS):
            values.append(value)
    return sorted(set(values), key=len, reverse=True)


def _redact_url(match: re.Match[str]) -> str:
    raw_url = match.group(0)
    try:
        parts = urlsplit(raw_url)
    except Exception:
        return raw_url

    netloc = parts.netloc
    if "@" in netloc:
        host = netloc.rsplit("@", 1)[1]
        netloc = f"{REDACTED}@{host}"

    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
    if query_pairs:
        safe_pairs = [
            (key, REDACTED if key.lower() in _SENSITIVE_QUERY_KEYS else value)
            for key, value in query_pairs
        ]
        query = urlencode(safe_pairs)
    else:
        query = parts.query

    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))


def redact_sensitive_text(text: Any) -> str:
    """Mask likely secrets while keeping enough context for debugging."""
    redacted = "" if text is None else str(text)

    for secret in _env_secret_values():
        redacted = redacted.replace(secret, REDACTED)

    redacted = re.sub(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        f"-----BEGIN PRIVATE KEY-----{REDACTED}-----END PRIVATE KEY-----",
        redacted,
        flags=re.DOTALL,
    )
    redacted = re.sub(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b", REDACTED, redacted)
    redacted = re.sub(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}\b", REDACTED, redacted)
    redacted = re.sub(r"\bsk-[A-Za-z0-9_\-]{8,}\b", "sk-[redacted]", redacted)
    redacted = re.sub(r"\bAIza[A-Za-z0-9_\-]{8,}\b", "AIza[redacted]", redacted)
    redacted = re.sub(
        r"(?i)\b(authorization|cookie|set-cookie|x-api-key)\s*[:=]\s*[^\n\r]+",
        lambda m: f"{m.group(1)}: {REDACTED}",
        redacted,
    )
    redacted = re.sub(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}", f"Bearer {REDACTED}", redacted)
    redacted = re.sub(
        r"(?i)\b(database_url(?:_prod|_staging)?|postgres(?:ql)?://)[^\s]+",
        lambda m: f"{m.group(1)}{REDACTED}" if m.group(1).startswith("postgres") else f"{m.group(1)}={REDACTED}",
        redacted,
    )
    redacted = re.sub(
        r"https?://[^\s<>'\"]+",
        _redact_url,
        redacted,
    )
    redacted = re.sub(
        r"(?i)([?&](?:token|key|password|secret|session|hash|initData|initdata)=)[^&\s]+",
        rf"\1{REDACTED}",
        redacted,
    )
    return redacted


def _last_traceback_frame(tb: Optional[TracebackType]) -> str:
    current = tb
    last: Optional[TracebackType] = None
    while current is not None:
        last = current
        current = current.tb_next
    if not last:
        return ""
    code = last.tb_frame.f_code
    return f"{code.co_filename}:{code.co_name}:{last.tb_lineno}"


def _normalize_for_fingerprint(value: str) -> str:
    normalized = redact_sensitive_text(value).lower()
    normalized = re.sub(r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b", "<uuid>", normalized)
    normalized = re.sub(r"\b[0-9a-f]{12,}\b", "<hex>", normalized)
    normalized = re.sub(r"\b\d{4}-\d{2}-\d{2}t[0-9:.+-]+z?\b", "<timestamp>", normalized)
    normalized = re.sub(r"\b\d+\b", "<num>", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def error_fingerprint(record: LogRecord) -> str:
    """Return a short stable fingerprint for duplicate admin alerts."""
    exc_type = ""
    tb_frame = ""
    if record.exc_info:
        exc_type_obj, _exc, traceback_obj = record.exc_info
        exc_type = getattr(exc_type_obj, "__name__", str(exc_type_obj))
        tb_frame = _last_traceback_frame(traceback_obj)

    source = "|".join(
        [
            record.name,
            record.levelname,
            exc_type,
            tb_frame or f"{record.pathname}:{record.funcName}",
            _normalize_for_fingerprint(record.getMessage()),
        ]
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]


def build_github_issue_title(fingerprint: str, logger_name: str, message: str) -> str:
    clean_message = re.sub(r"\s+", " ", redact_sensitive_text(message)).strip()
    clean_message = clean_message[:90] or "System error"
    return f"System error {fingerprint}: {logger_name}: {clean_message}"[:230]


def build_github_issue_body(
    *,
    fingerprint: str,
    admin_message: str,
    requested_by: str,
    environment: Optional[str] = None,
) -> str:
    env = environment or os.getenv("ENVIRONMENT") or os.getenv("ENV") or "unknown"
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    safe_message = redact_sensitive_text(admin_message).strip()
    return "\n".join(
        [
            "Created from Telegram admin error alert.",
            "",
            f"- Fingerprint: `{fingerprint}`",
            f"- Environment: `{env}`",
            f"- Requested by: `{requested_by}`",
            f"- Created at: `{now}`",
            "",
            "```text",
            safe_message[:12000],
            "```",
        ]
    )


def build_github_issue_url(
    *,
    repository: str,
    title: str,
    body: str,
    labels: Optional[list[str]] = None,
    max_url_length: int = 3500,
) -> str:
    """Build a prefilled GitHub issue URL without requiring a server token."""
    safe_repository = (repository or "").strip().strip("/")
    if "/" not in safe_repository:
        raise ValueError("repository must be in OWNER/REPO format")

    safe_title = redact_sensitive_text(title).strip()[:230] or "System error"
    safe_body = redact_sensitive_text(body).strip()
    label_value = ",".join(label.strip() for label in (labels or []) if label.strip())
    base_url = f"https://github.com/{safe_repository}/issues/new"

    def _build_url(body_value: str) -> str:
        params = {"title": safe_title, "body": body_value}
        if label_value:
            params["labels"] = label_value
        return f"{base_url}?{urlencode(params)}"

    issue_url = _build_url(safe_body)
    if len(issue_url) <= max_url_length:
        return issue_url

    suffix = "\n\n[Body truncated to keep the prefilled GitHub issue URL short.]"
    low = 0
    high = max(0, len(safe_body))
    best_body = suffix.strip()
    while low <= high:
        mid = (low + high) // 2
        candidate_body = safe_body[:mid].rstrip() + suffix
        candidate_url = _build_url(candidate_body)
        if len(candidate_url) <= max_url_length:
            best_body = candidate_body
            low = mid + 1
        else:
            high = mid - 1
    return _build_url(best_body)


def dispatch_github_workflow(
    *,
    repository: str,
    workflow_file: str,
    ref: str,
    token: str,
    inputs: Optional[dict[str, str]] = None,
) -> None:
    """Dispatch a GitHub Actions workflow."""
    api_url = f"https://api.github.com/repos/{repository}/actions/workflows/{workflow_file}/dispatches"
    payload: dict[str, Any] = {"ref": ref}
    if inputs:
        payload["inputs"] = inputs

    request = Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=10) as response:
            status = getattr(response, "status", response.getcode())
            if status not in {201, 204}:
                raise RuntimeError(f"Unexpected GitHub API status: {status}")
    except HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub dispatch failed with {exc.code}: {body_text[:400]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach GitHub API: {exc}") from exc
