"""
Unified logging module for Zana AI bot.
Supports dual output: console (for Docker logs) and Logtail (for centralized logging).
"""
import logging
import os
import sys
from typing import Any, Dict, Optional

# Try to import Logtail handler
try:
    from logtail import LogtailHandler
    LOGTAIL_AVAILABLE = True
except ImportError:
    LOGTAIL_AVAILABLE = False
    LogtailHandler = None


class StructuredFormatter(logging.Formatter):
    """Formatter that supports structured logging (dicts) for Logtail."""
    
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
    
    # Prevent duplicate handlers if logger already exists
    if logger.handlers:
        _loggers[name] = logger
        return logger
    
    # Console handler (always present)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ConsoleFormatter())
    logger.addHandler(console_handler)
    
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
