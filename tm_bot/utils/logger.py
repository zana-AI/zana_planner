"""
Unified logging module for Xaana AI bot.
Supports:
  - Console (stdout) -> always; captured by Docker as `docker logs`
  - Logtail (Better Stack) -> when LOGTAIL_SOURCE_TOKEN is set
  - File on VM -> when LOG_FILE_PATH is set (persistent, grep-able source of truth)
  - Telegram admin alerts -> when bot token and ADMIN_IDS are configured
"""
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Dict, Optional, Set
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

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
    ) -> None:
        super().__init__(level=logging.ERROR)
        self.bot_token = bot_token.strip()
        self.admin_ids = tuple(sorted(admin_ids))
        self.tag = tag
        self.timeout_seconds = timeout_seconds
        self._is_admin_error_handler = True
        self.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.ERROR:
            return

        try:
            message = self._build_message(record)
            # Telegram sendMessage hard-limit is 4096 chars.
            if len(message) > 4096:
                message = f"{message[:4093]}..."
            for admin_id in self.admin_ids:
                self._send_message(admin_id, message)
        except Exception as exc:  # pragma: no cover - best effort logging path
            try:
                sys.stderr.write(f"Failed to send admin error notification: {exc}\n")
            except Exception:
                pass

    def _build_message(self, record: logging.LogRecord) -> str:
        timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        error_text = record.getMessage()
        parts = [
            self.tag,
            f"time={timestamp}",
            f"level={record.levelname}",
            f"logger={record.name}",
            "",
            error_text,
        ]

        if record.exc_info and self.formatter:
            traceback_text = self.formatter.formatException(record.exc_info)
            if traceback_text:
                parts.extend(["", "traceback:", traceback_text])

        return "\n".join(parts)

    def _send_message(self, admin_id: int, text: str) -> None:
        api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = urlencode(
            {
                "chat_id": str(admin_id),
                "text": text,
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")
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

    return TelegramAdminErrorHandler(resolved_token, admin_ids)


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
