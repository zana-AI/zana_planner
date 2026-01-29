"""Safe entrypoint that logs import/runtime failures to Logtail/console."""

import logging
import sys

from utils.logger import get_logger

logger = get_logger(__name__)


def _install_excepthook():
    def _hook(exc_type, exc, tb):
        try:
            logger.exception("unhandled_exception", exc_info=(exc_type, exc, tb))
        finally:
            sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook


def main():
    _install_excepthook()
    try:
        from planner_bot import main as bot_main  # noqa: WPS433
    except Exception:
        logger.exception("failed_to_import_planner_bot")
        sys.exit(1)

    try:
        bot_main()
    except Exception:
        logger.exception("bot_runtime_failure")
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
