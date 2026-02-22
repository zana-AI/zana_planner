"""
Unified logging module for Xaana AI bot.
Supports:
  - Console (stdout) → always; captured by Docker as `docker logs`
  - Logtail (Better Stack) → when LOGTAIL_SOURCE_TOKEN is set
  - File on VM → when LOG_FILE_PATH is set (persistent, grep-able source of truth)
"""
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo
from logging.handlers import RotatingFileHandler

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
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
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
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
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
            return f"{self.formatTime(record, self.datefmt)} - {record.name} - {record.levelname} - {json.dumps(log_data, default=str)}"
        return super().format(record)


# Global logger cache
_loggers: Dict[str, logging.Logger] = {}


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
        _loggers[name] = logger
        return logger
    
    # Console handler (always present)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ConsoleFormatter())
    logger.addHandler(console_handler)
    
    # File handler (if configured) — persistent on VM for debugging
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
            logger.info({"event": "logger_init", "module": name, "file_logging_enabled": True, "path": log_file_path})
        except Exception as e:
            logger.warning(f"Failed to add file handler for {log_file_path}: {e}. Skipping file logging.")
    
    # Logtail handler (if configured)
    logtail_token = os.getenv("LOGTAIL_SOURCE_TOKEN")
    logtail_host = os.getenv("LOGTAIL_INGEST_HOST", "in.logtail.com")
    
    if LOGTAIL_AVAILABLE and logtail_token:
        try:
            logtail_handler = LogtailHandler(
                source_token=logtail_token,
                host=logtail_host
            )
            logtail_handler.setLevel(logging.INFO)
            logtail_handler.setFormatter(StructuredFormatter())
            logger.addHandler(logtail_handler)
            logger.info({"event": "logger_init", "module": name, "logtail_enabled": True})
        except Exception as e:
            # Graceful fallback: log to console only
            logger.warning(f"Failed to initialize Logtail handler: {e}. Using console logging only.")
    else:
        if not LOGTAIL_AVAILABLE:
            logger.debug("logtail-python not available. Install with: pip install logtail-python")
        if not logtail_token:
            logger.debug("LOGTAIL_SOURCE_TOKEN not set. Logtail logging disabled.")
    
    _loggers[name] = logger
    return logger
