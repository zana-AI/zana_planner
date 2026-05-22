"""
Unified logging module for Xaana AI bot.
Supports:
  - Console (stdout) -> always; captured by Docker as `docker logs`
  - Logtail (Better Stack) -> when LOGTAIL_SOURCE_TOKEN is set
  - File on VM -> when LOG_FILE_PATH is set (persistent, grep-able source of truth)
  - Telegram admin alerts -> when bot token and ADMIN_IDS are configured
"""
import logging
import json
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Dict, Optional, Set
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from services.admin_ops_service import (
    DEFAULT_DEDUPE_SECONDS,
    ErrorAlertRateLimiter,
    build_github_issue_body,
    build_github_issue_title,
    build_github_issue_url,
    error_fingerprint,
    redact_sensitive_text,
)

# Try to import Logtail handler
try:
    from logtail import LogtailHandler

    LOGTAIL_AVAILABLE = True
except ImportError:
    LOGTAIL_AVAILABLE = False
    LogtailHandler = None


class StructuredFormatter(logging.Formatter):
    """Formatter that supports structured logging (dicts) for Logtail."""

    def __init__(self):
        super().__init__()
        self.paris_tz = ZoneInfo("Europe/Paris")

    def formatTime(self, record: logging.LogRecord, datefmt: Optional[str] = None) -> str:
        """Format time in Paris timezone."""
        dt = datetime.fromtimestamp(record.created, tz=self.paris_tz)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()

    def format(self, record: logging.LogRecord) -> str:
        # If the message is a dict, convert it to JSON-like string
        if isinstance(record.msg, dict):
            import json

            # Add standard fields
            log_data = {
                "message": record.msg.get("message", ""),
                "level": record.levelname,
                "module": record.module,
                "timestamp": self.formatTime(record, self.datefmt),
            }
            # Merge in any additional fields from the dict
            log_data.update({k: v for k, v in record.msg.items() if k != "message"})
            return json.dumps(log_data, default=str)
        return super().format(record)


class ConsoleFormatter(logging.Formatter):
    """Human-readable formatter for console output."""

    def __init__(self):
        super().__init__(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self.paris_tz = ZoneInfo("Europe/Paris")

    def formatTime(self, record: logging.LogRecord, datefmt: Optional[str] = None) -> str:
        """Format time in Paris timezone."""
        dt = datetime.fromtimestamp(record.created, tz=self.paris_tz)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()


class FileFormatter(logging.Formatter):
    """One-line formatter for file output; supports dict messages as JSON."""

    def __init__(self):
        super().__init__(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self.paris_tz = ZoneInfo("Europe/Paris")

    def formatTime(self, record: logging.LogRecord, datefmt: Optional[str] = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=self.paris_tz)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()

    def format(self, record: logging.LogRecord) -> str:
        if isinstance(record.msg, dict):
            import json

            log_data = {
                "message": record.msg.get("message", ""),
                "level": record.levelname,
                "module": record.module,
                "timestamp": self.formatTime(record, self.datefmt),
            }
            log_data.update({k: v for k, v in record.msg.items() if k != "message"})
            # One line per log for easy grep/tail
            return (
                f"{self.formatTime(record, self.datefmt)} - {record.name} - "
                f"{record.levelname} - {json.dumps(log_data, default=str)}"
            )
        return super().format(record)


class TelegramAdminErrorHandler(logging.Handler):
    """Send ERROR and above logs directly to configured Telegram admins."""

    def __init__(
        self,
        bot_token: str,
        admin_ids: Set[int],
        tag: str = "#system_error",
        timeout_seconds: float = 4.0,
        dedupe_seconds: Optional[int] = None,
    ) -> None:
        super().__init__(level=logging.ERROR)
        self.bot_token = bot_token.strip()
        self.admin_ids = tuple(sorted(admin_ids))
        self.tag = tag
        self.timeout_seconds = timeout_seconds
        self.rate_limiter = ErrorAlertRateLimiter(
            DEFAULT_DEDUPE_SECONDS if dedupe_seconds is None else dedupe_seconds
        )
        self._is_admin_error_handler = True
        self.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.ERROR:
            return

        try:
            fingerprint = error_fingerprint(record)
            decision = self.rate_limiter.check(fingerprint)
            if not decision.should_send:
                return
            message = self._build_message(
                record,
                fingerprint=fingerprint,
                suppressed_count=decision.suppressed_count,
            )
            issue_url = self._build_issue_url(record, fingerprint=fingerprint)
            reply_markup = self._build_reply_markup(issue_url)
            for admin_id in self.admin_ids:
                self._send_message(admin_id, message, reply_markup=reply_markup)
        except Exception as exc:  # pragma: no cover - best effort logging path
            try:
                sys.stderr.write(f"Failed to send admin error notification: {exc}\n")
            except Exception:
                pass

    @staticmethod
    def _html_escape(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _build_message(
        self,
        record: logging.LogRecord,
        *,
        fingerprint: Optional[str] = None,
        suppressed_count: int = 0,
    ) -> str:
        _OPEN = "<blockquote expandable>"
        _CLOSE = "</blockquote>"
        _MAX = 4096

        timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        error_text = redact_sensitive_text(record.getMessage())

        header_lines = [
            self.tag,
            f"time={timestamp}",
            f"level={record.levelname}",
            f"logger={record.name}",
        ]
        if fingerprint:
            header_lines.append(f"fingerprint={fingerprint}")
        if suppressed_count:
            header_lines.append(f"suppressed_since_last={suppressed_count}")
        header = "\n".join(header_lines)

        body_parts = [self._html_escape(error_text)]

        if record.exc_info and self.formatter:
            traceback_text = self.formatter.formatException(record.exc_info)
            if traceback_text:
                body_parts.extend([
                    "",
                    "traceback:",
                    self._html_escape(redact_sensitive_text(traceback_text)),
                ])

        body = "\n".join(body_parts)

        # Truncate only the inner body so tags are never split.
        # overhead = header + "\n\n" + _OPEN + _CLOSE
        max_body = _MAX - len(header) - 2 - len(_OPEN) - len(_CLOSE)
        if len(body) > max_body:
            body = body[:max_body - 3] + "..."

        return f"{header}\n\n{_OPEN}{body}{_CLOSE}"

    def _build_issue_plaintext(self, record: logging.LogRecord, *, fingerprint: str) -> str:
        body_parts = [redact_sensitive_text(record.getMessage())]
        if record.exc_info and self.formatter:
            traceback_text = self.formatter.formatException(record.exc_info)
            if traceback_text:
                body_parts.extend(["", "traceback:", redact_sensitive_text(traceback_text)])
        timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        return "\n".join([
            self.tag,
            f"time={timestamp}",
            f"level={record.levelname}",
            f"logger={record.name}",
            f"fingerprint={fingerprint}",
            "",
            "\n".join(body_parts),
        ])

    def _build_issue_url(self, record: logging.LogRecord, *, fingerprint: str) -> str:
        repository = (
            os.getenv("GITHUB_ISSUE_REPOSITORY")
            or os.getenv("GITHUB_DEPLOY_REPOSITORY")
            or os.getenv("GITHUB_REPOSITORY")
            or "zana-AI/zana_planner"
        ).strip().strip("/")
        if "/" not in repository:
            repository = "zana-AI/zana_planner"
        plain_message = self._build_issue_plaintext(record, fingerprint=fingerprint)
        title = build_github_issue_title(
            fingerprint,
            record.name,
            record.getMessage(),
        )
        body = build_github_issue_body(
            fingerprint=fingerprint,
            admin_message=plain_message,
            requested_by="telegram-admin",
        )
        labels = [
            label.strip()
            for label in os.getenv("GITHUB_ISSUE_LABELS", "bug,admin-error").split(",")
            if label.strip()
        ]
        return build_github_issue_url(
            repository=repository,
            title=title,
            body=body,
            labels=labels,
        )

    @staticmethod
    def _build_reply_markup(issue_url: str) -> str:
        return json.dumps(
            {
                "inline_keyboard": [
                    [
                        {
                            "text": "Create GitHub issue",
                            "url": issue_url,
                        }
                    ]
                ]
            },
            separators=(",", ":"),
        )

    def _send_message(self, admin_id: int, text: str, reply_markup: Optional[str] = None) -> None:
        api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        fields = {
            "chat_id": str(admin_id),
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
        if reply_markup:
            fields["reply_markup"] = reply_markup
        payload = urlencode(fields).encode("utf-8")
        request = Request(api_url, data=payload, method="POST")
        with urlopen(request, timeout=self.timeout_seconds):
            pass


def _parse_admin_ids(raw: str) -> Set[int]:
    admin_ids: Set[int] = set()
    for item in (raw or "").split(","):
        value = item.strip()
        if not value:
            continue
        try:
            admin_ids.add(int(value))
        except ValueError:
            continue
    return admin_ids


def _build_admin_error_handler(
    bot_token: Optional[str] = None,
) -> Optional[TelegramAdminErrorHandler]:
    resolved_token = (
        bot_token or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or ""
    ).strip()
    admin_ids = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))

    if not resolved_token or not admin_ids:
        return None

    raw_dedupe_seconds = os.getenv("ADMIN_ERROR_DEDUPE_SECONDS", str(DEFAULT_DEDUPE_SECONDS))
    try:
        dedupe_seconds = int(raw_dedupe_seconds)
    except ValueError:
        dedupe_seconds = DEFAULT_DEDUPE_SECONDS

    return TelegramAdminErrorHandler(
        resolved_token,
        admin_ids,
        dedupe_seconds=dedupe_seconds,
    )


def _remove_admin_error_handlers(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        if getattr(handler, "_is_admin_error_handler", False):
            logger.removeHandler(handler)


# Global logger cache
_loggers: Dict[str, logging.Logger] = {}
_admin_error_handler: Optional[logging.Handler] = None


def configure_admin_error_notifications(bot_token: Optional[str] = None) -> bool:
    """
    Configure Telegram alerts for ERROR logs and attach handler to all known loggers.

    Args:
        bot_token: Optional explicit bot token. Falls back to env vars.

    Returns:
        True when notification handler is configured; False otherwise.
    """
    global _admin_error_handler

    handler = _build_admin_error_handler(bot_token=bot_token)
    if handler is None:
        return False

    _admin_error_handler = handler
    root_logger = logging.getLogger()
    _remove_admin_error_handlers(root_logger)
    root_logger.addHandler(handler)
    for existing_logger in _loggers.values():
        _remove_admin_error_handlers(existing_logger)
        existing_logger.addHandler(handler)
    return True


def get_logger(name: str) -> logging.Logger:
    """
    Get or create a logger with console and Logtail handlers.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    # Prevent duplicate logs when root logger is configured elsewhere.
    logger.propagate = False

    # Prevent duplicate handlers if logger already exists
    if logger.handlers:
        if _admin_error_handler is None:
            configure_admin_error_notifications()
        if _admin_error_handler is not None:
            _remove_admin_error_handlers(logger)
            logger.addHandler(_admin_error_handler)
        _loggers[name] = logger
        return logger

    # Console handler (always present)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ConsoleFormatter())
    logger.addHandler(console_handler)

    # File handler (if configured) - persistent on VM for debugging
    log_file_path = os.getenv("LOG_FILE_PATH")
    if log_file_path:
        try:
            log_dir = os.path.dirname(log_file_path)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_file_path,
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(FileFormatter())
            logger.addHandler(file_handler)
            logger.info(
                {
                    "event": "logger_init",
                    "module": name,
                    "file_logging_enabled": True,
                    "path": log_file_path,
                }
            )
        except Exception as e:  # pragma: no cover - best effort logging path
            logger.warning(
                f"Failed to add file handler for {log_file_path}: {e}. "
                "Skipping file logging."
            )

    # Logtail handler (if configured)
    logtail_token = os.getenv("LOGTAIL_SOURCE_TOKEN")
    logtail_host = os.getenv("LOGTAIL_INGEST_HOST", "in.logtail.com")

    if LOGTAIL_AVAILABLE and logtail_token:
        try:
            logtail_handler = LogtailHandler(source_token=logtail_token, host=logtail_host)
            logtail_handler.setLevel(logging.INFO)
            logtail_handler.setFormatter(StructuredFormatter())
            logger.addHandler(logtail_handler)
            logger.info({"event": "logger_init", "module": name, "logtail_enabled": True})
        except Exception as e:  # pragma: no cover - best effort logging path
            # Graceful fallback: log to console only
            logger.warning(
                f"Failed to initialize Logtail handler: {e}. "
                "Using console logging only."
            )
    else:
        if not LOGTAIL_AVAILABLE:
            logger.debug("logtail-python not available. Install with: pip install logtail-python")
        if not logtail_token:
            logger.debug("LOGTAIL_SOURCE_TOKEN not set. Logtail logging disabled.")

    if _admin_error_handler is None:
        configure_admin_error_notifications()
    if _admin_error_handler is not None:
        _remove_admin_error_handlers(logger)
        logger.addHandler(_admin_error_handler)

    _loggers[name] = logger
    return logger
