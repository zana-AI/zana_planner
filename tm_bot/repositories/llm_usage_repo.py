"""Repository for per-call LLM usage telemetry (model + token counts)."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from db.postgres_db import get_db_session, utc_now_iso
from llms.llm_model_config import estimate_cost_usd

logger = logging.getLogger(__name__)

# Single background worker so logging never blocks the request path.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="llm-usage-log")


def _insert_row(payload: Dict[str, Any]) -> None:
    try:
        with get_db_session() as session:
            session.execute(
                text(
                    """
                    INSERT INTO llm_usage_logs (
                        created_at_utc, provider, model_name, role,
                        input_tokens, output_tokens, total_tokens,
                        latency_ms, success, error_type
                    ) VALUES (
                        :created_at_utc, :provider, :model_name, :role,
                        :input_tokens, :output_tokens, :total_tokens,
                        :latency_ms, :success, :error_type
                    )
                    """
                ),
                payload,
            )
    except Exception as exc:  # pragma: no cover - telemetry must not crash the bot
        logger.warning("Failed to persist llm_usage row: %s", exc)


def log_usage(
    *,
    provider: str,
    model_name: str,
    role: Optional[str],
    input_tokens: int,
    output_tokens: int,
    latency_ms: Optional[int] = None,
    success: bool = True,
    error_type: Optional[str] = None,
) -> None:
    """Fire-and-forget insert into llm_usage_logs."""
    payload = {
        "created_at_utc": utc_now_iso(),
        "provider": (provider or "").strip().lower() or "unknown",
        "model_name": (model_name or "").strip() or "unknown",
        "role": (role or None),
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "total_tokens": int((input_tokens or 0) + (output_tokens or 0)),
        "latency_ms": int(latency_ms) if latency_ms is not None else None,
        "success": bool(success),
        "error_type": error_type,
    }
    try:
        _executor.submit(_insert_row, payload)
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to enqueue llm_usage log: %s", exc)


def get_summary(window_hours: int = 24) -> List[Dict[str, Any]]:
    """Aggregate usage by (provider, model, role) for the last N hours.

    Returns a list of rows with calls, in/out/total tokens, avg latency,
    error count, and estimated USD cost.
    """
    hours = max(1, min(int(window_hours or 24), 24 * 90))
    with get_db_session() as session:
        rows = session.execute(
            text(
                """
                SELECT
                    provider,
                    model_name,
                    COALESCE(role, '') AS role,
                    COUNT(*) AS calls,
                    COALESCE(SUM(input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(AVG(latency_ms), 0) AS avg_latency_ms,
                    SUM(CASE WHEN success THEN 0 ELSE 1 END) AS errors
                FROM llm_usage_logs
                WHERE created_at_utc >= (NOW() AT TIME ZONE 'UTC' - (:hours || ' hours')::interval)::text
                GROUP BY provider, model_name, COALESCE(role, '')
                ORDER BY total_tokens DESC, calls DESC
                """
            ),
            {"hours": hours},
        ).mappings().fetchall()

    summary: List[Dict[str, Any]] = []
    for row in rows:
        in_tok = int(row["input_tokens"] or 0)
        out_tok = int(row["output_tokens"] or 0)
        cost = estimate_cost_usd(row["model_name"], in_tok, out_tok)
        summary.append(
            {
                "provider": row["provider"],
                "model_name": row["model_name"],
                "role": row["role"] or None,
                "calls": int(row["calls"] or 0),
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "total_tokens": int(row["total_tokens"] or 0),
                "avg_latency_ms": int(row["avg_latency_ms"] or 0),
                "errors": int(row["errors"] or 0),
                "estimated_cost_usd": cost,
            }
        )
    return summary


def get_totals(window_hours: int = 24) -> Dict[str, Any]:
    """Top-line totals across all models for the last N hours."""
    hours = max(1, min(int(window_hours or 24), 24 * 90))
    with get_db_session() as session:
        row = session.execute(
            text(
                """
                SELECT
                    COUNT(*) AS calls,
                    COALESCE(SUM(input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    SUM(CASE WHEN success THEN 0 ELSE 1 END) AS errors
                FROM llm_usage_logs
                WHERE created_at_utc >= (NOW() AT TIME ZONE 'UTC' - (:hours || ' hours')::interval)::text
                """
            ),
            {"hours": hours},
        ).mappings().fetchone()

    calls = int((row or {}).get("calls") or 0)
    in_tok = int((row or {}).get("input_tokens") or 0)
    out_tok = int((row or {}).get("output_tokens") or 0)
    total_tok = int((row or {}).get("total_tokens") or 0)
    errors = int((row or {}).get("errors") or 0)
    return {
        "calls": calls,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "total_tokens": total_tok,
        "errors": errors,
    }
