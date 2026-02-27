#!/usr/bin/env python3
"""
Run Alembic migrations for both PostgreSQL databases (prod + staging).

Reads /opt/zana-config/.env.prod and /opt/zana-config/.env.staging to pick up
DATABASE_URL_PROD and DATABASE_URL_STAGING, then runs Alembic migrations
against each database that is configured.

Usage (on the server):
    sudo python3 scripts/run_migrations.py            # both DBs
    sudo python3 scripts/run_migrations.py --prod     # prod only
    sudo python3 scripts/run_migrations.py --staging  # staging only

Env-file paths can be overridden:
    ZANA_ENV_PROD=/path/.env.prod ZANA_ENV_STAGING=/path/.env.staging \\
        sudo -E python3 scripts/run_migrations.py
"""

import argparse
import os
import sys
from pathlib import Path

# Add project root to path so alembic env.py can import db modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import os as os_module

# Import only what we need for migrations (avoid bot initialization)
from alembic.config import Config
from alembic import command


# ---------------------------------------------------------------------------
# Env-file loader
# ---------------------------------------------------------------------------

def _load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines into os.environ.
    Skips empty lines and # comments.
    Does NOT overwrite variables already set in the environment."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os_module.environ:
                os_module.environ[key] = value


def _load_both_env_files() -> None:
    """Load prod and staging env files from /opt/zana-config/ (or overrides)."""
    prod_file = Path(os_module.getenv("ZANA_ENV_PROD", "/opt/zana-config/.env.prod"))
    staging_file = Path(os_module.getenv("ZANA_ENV_STAGING", "/opt/zana-config/.env.staging"))
    for path in (prod_file, staging_file):
        if path.exists():
            print(f"  Loading env file: {path}")
            _load_env_file(path)
        else:
            print(f"  (env file not found, skipping: {path})")


# ---------------------------------------------------------------------------
# Table-count helper
# ---------------------------------------------------------------------------

def _print_table_counts(database_url: str) -> None:
    """Print name and row count for every table in the public schema."""
    try:
        import psycopg2
        from psycopg2 import sql as pgsql
    except ImportError:
        print("  (Install psycopg2 to see table counts)")
        return
    try:
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        tables = [row[0] for row in cur.fetchall()]
        if not tables:
            print("  No tables in public schema.")
            cur.close()
            conn.close()
            return
        print("\n  Table row counts:")
        max_name = max(len(t) for t in tables)
        for name in tables:
            cur.execute(pgsql.SQL("SELECT COUNT(*) FROM {}").format(pgsql.Identifier(name)))
            count = cur.fetchone()[0]
            print(f"    {name:<{max_name}}  {count:>10,} rows")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"  (Could not list table counts: {e})")


# ---------------------------------------------------------------------------
# Per-DB migration runner
# ---------------------------------------------------------------------------

def _run_migrations_for(label: str, database_url: str) -> bool:
    """Run Alembic migrations against a single database URL.
    Returns True on success, False on failure."""
    alembic_ini = project_root / "tm_bot" / "db" / "alembic.ini"
    if not alembic_ini.exists():
        print(f"  ERROR: alembic.ini not found at {alembic_ini}")
        return False

    safe_url = database_url.split("@")[1] if "@" in database_url else "***"
    print(f"\n{'='*60}")
    print(f"  [{label}] → {safe_url}")
    print(f"{'='*60}")

    # Temporarily set DATABASE_URL so alembic env.py picks it up regardless of
    # ENVIRONMENT variable (we manage the URL explicitly here).
    old_env = os_module.environ.get("DATABASE_URL")
    os_module.environ["DATABASE_URL"] = database_url

    try:
        alembic_cfg = Config(str(alembic_ini))
        alembic_cfg.set_main_option("sqlalchemy.url", database_url)
        print("  Running Alembic upgrade head …")
        command.upgrade(alembic_cfg, "head")
        print(f"  ✓ Migrations completed for [{label}]")
        _print_table_counts(database_url)
        return True
    except Exception as e:
        print(f"  ✗ Migration failed for [{label}]: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Restore original DATABASE_URL
        if old_env is None:
            os_module.environ.pop("DATABASE_URL", None)
        else:
            os_module.environ["DATABASE_URL"] = old_env


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Alembic migrations against prod and/or staging databases."
    )
    parser.add_argument("--prod", action="store_true", help="Run only against the production DB")
    parser.add_argument("--staging", action="store_true", help="Run only against the staging DB")
    args = parser.parse_args()

    # Default: run both unless a specific flag was given
    run_prod = args.prod or (not args.prod and not args.staging)
    run_staging = args.staging or (not args.prod and not args.staging)

    print("=== Zana DB Migrations ===")
    print("Loading env files …")
    _load_both_env_files()

    results: list[tuple[str, bool]] = []

    if run_prod:
        url = os_module.getenv("DATABASE_URL_PROD")
        if url:
            ok = _run_migrations_for("PRODUCTION", url)
            results.append(("PRODUCTION", ok))
        else:
            print("\n  [PRODUCTION] skipped — DATABASE_URL_PROD not set")
            results.append(("PRODUCTION", False))

    if run_staging:
        url = os_module.getenv("DATABASE_URL_STAGING")
        if url:
            ok = _run_migrations_for("STAGING", url)
            results.append(("STAGING", ok))
        else:
            print("\n  [STAGING] skipped — DATABASE_URL_STAGING not set")
            results.append(("STAGING", False))

    # Summary
    print(f"\n{'='*60}")
    print("  Summary:")
    all_ok = True
    for label, ok in results:
        status = "✓" if ok else "✗"
        print(f"    {status} {label}")
        if not ok:
            all_ok = False
    print(f"{'='*60}\n")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
