import os
import sys

import pytest

# Ensure tm_bot is importable in tests (e.g., `import llms...`).
TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.insert(0, TM_BOT_DIR)


def _postgres_available() -> bool:
    """Return True if PostgreSQL is available for tests (psycopg2 + DATABASE_URL)."""
    try:
        import psycopg2  # noqa: F401
    except ImportError:
        return False
    if os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_STAGING"):
        return True
    return False


def pytest_collection_modifyitems(config, items):
    """Skip tests marked requires_postgres when PostgreSQL is not available."""
    if _postgres_available():
        return
    skip = pytest.mark.skip(
        reason="PostgreSQL required: install psycopg2-binary, set DATABASE_URL or DATABASE_URL_STAGING, and run scripts/run_migrations.py so DB is at schema head"
    )
    for item in items:
        if "requires_postgres" in item.keywords:
            item.add_marker(skip)

