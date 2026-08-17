"""
Shared computation for a club's rolling 7-day leaderboard.

Used by both the webapp's `/clubs/{club_id}/leaderboard` route (for the
Community tab in the Mini App) and the Telegram bot's scheduled leaderboard
image (`club_reminder_service.send_due_club_leaderboards`). Kept framework-
agnostic (plain dicts, no FastAPI/Pydantic dependency) so it's usable from
either process without pulling webapp code into the bot.
"""
from __future__ import annotations

import base64
import mimetypes
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from db.postgres_db import get_db_session

DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _date_key(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _calculate_freeze_streak(activity_dates: List[date], today: date, freeze_budget: int = 2) -> int:
    dates = sorted({d for d in activity_dates if d <= today}, reverse=True)
    if not dates:
        return 0

    freezes_remaining = max(0, int(freeze_budget))
    initial_missed_days = max(0, (today - dates[0]).days - 1)
    if initial_missed_days > freezes_remaining:
        return 0

    freezes_remaining -= initial_missed_days
    streak = 1
    previous = dates[0]
    for check_date in dates[1:]:
        missed_days = max(0, (previous - check_date).days - 1)
        if missed_days > freezes_remaining:
            break
        freezes_remaining -= missed_days
        streak += 1
        previous = check_date
    return streak


def _display_name_key(member: dict) -> str:
    return str(
        member.get("first_name")
        or member.get("username")
        or member.get("user_id")
        or ""
    ).lower()


def _sort_timestamp_desc(value: Optional[str]) -> float:
    if not value:
        return 0.0
    try:
        return -datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _rank_club_leaderboard_members(
    *,
    members: list[dict],
    promises: list[dict],
    actions_by_member_promise: dict[tuple[str, str], dict],
    today: date,
    limit: int,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    name_by_user: dict[str, str] = {}
    window_dates = [today - timedelta(days=offset) for offset in range(6, -1, -1)]

    for member in members:
        user_id = str(member["user_id"])
        name_by_user[user_id] = _display_name_key(member)
        breakdown: List[Dict[str, Any]] = []
        daily_totals = {
            activity_date: {"checkins": 0, "duration_hours": 0.0, "score_sum": 0.0, "score_count": 0}
            for activity_date in window_dates
        }
        activity_dates: set[date] = set()
        last_activity_at_utc: Optional[str] = None
        total_duration_hours = 0.0
        total_checkins = 0

        for promise in promises:
            promise_uuid = str(promise["promise_uuid"])
            metric_type = str(promise.get("metric_type") or "hours")
            target_value = float(promise.get("target_value") or (7.0 if metric_type == "count" else 1.0))
            stats = actions_by_member_promise.get((user_id, promise_uuid), {})
            activity_days_set = set(stats.get("activity_days") or stats.get("active_days") or [])
            checkin_days_set = set(stats.get("checkin_days") or stats.get("active_days") or [])
            daily_stats = stats.get("daily") or {}
            duration_hours = float(stats.get("duration_hours") or 0.0)
            checkin_count = int(stats.get("checkin_count") or 0)
            last_at = stats.get("last_activity_at_utc")

            activity_dates.update(activity_days_set)
            total_duration_hours += duration_hours
            total_checkins += checkin_count
            if last_at and (not last_activity_at_utc or str(last_at) > last_activity_at_utc):
                last_activity_at_utc = str(last_at)

            if metric_type == "count":
                achieved_value = float(len(checkin_days_set))
                active_days_count = len(checkin_days_set)
            else:
                achieved_value = duration_hours
                active_days_count = len(activity_days_set)
            progress_percent = min(round((achieved_value / target_value) * 100, 1), 100.0) if target_value > 0 else 0.0

            for activity_date in window_dates:
                day_stats = daily_stats.get(activity_date) or daily_stats.get(activity_date.isoformat()) or {}
                day_checkins = int(day_stats.get("checkins") or (1 if activity_date in checkin_days_set else 0))
                day_duration_hours = float(day_stats.get("duration_hours") or 0.0)
                if not daily_stats and metric_type != "count" and activity_date in activity_days_set and len(activity_days_set) == 1:
                    day_duration_hours = duration_hours

                day_scored = day_stats.get("score")
                if day_scored is not None:
                    # Non-binary scored check-in (challenge daily quiz) — rank by how well.
                    day_score = min(max(float(day_scored), 0.0), 100.0)
                elif metric_type == "count":
                    day_score = 100.0 if day_checkins > 0 else 0.0
                else:
                    daily_target = max(target_value / 7.0, 0.25)
                    day_score = min(round((day_duration_hours / daily_target) * 100, 1), 100.0)

                totals = daily_totals[activity_date]
                totals["checkins"] += day_checkins
                totals["duration_hours"] += day_duration_hours
                totals["score_sum"] += day_score
                totals["score_count"] += 1

            breakdown.append({
                "promise_uuid": promise_uuid,
                "promise_text": str(promise.get("promise_text") or "Club promise"),
                "metric_type": metric_type,
                "target_value": target_value,
                "achieved_value": round(achieved_value, 2),
                "active_days": active_days_count,
                "duration_hours": round(duration_hours, 2),
                "checkin_count": checkin_count,
                "progress_percent": progress_percent,
            })

        score_percent = (
            round(sum(item["progress_percent"] for item in breakdown) / len(breakdown), 1)
            if breakdown
            else 0.0
        )
        daily_activity = [
            {
                "date": activity_date.isoformat(),
                "active": totals["checkins"] > 0 or totals["duration_hours"] > 0,
                "checkins": int(totals["checkins"]),
                "duration_hours": round(float(totals["duration_hours"]), 2),
                "score_percent": (
                    round(float(totals["score_sum"]) / int(totals["score_count"]), 1)
                    if int(totals["score_count"]) > 0
                    else 0.0
                ),
            }
            for activity_date, totals in daily_totals.items()
        ]
        rows.append({
            "rank": 0,
            "user_id": user_id,
            "first_name": str(member["first_name"]) if member.get("first_name") else None,
            "username": str(member["username"]) if member.get("username") else None,
            "avatar_path": str(member["avatar_path"]) if member.get("avatar_path") else None,
            "score_percent": score_percent,
            "active_days": len(activity_dates),
            "duration_hours": round(total_duration_hours, 2),
            "checkin_count": total_checkins,
            "freeze_streak": _calculate_freeze_streak(list(activity_dates), today),
            "last_activity_at_utc": last_activity_at_utc,
            "daily_activity": daily_activity,
            "breakdown": breakdown,
        })

    rows.sort(
        key=lambda row: (
            -row["score_percent"],
            _sort_timestamp_desc(row["last_activity_at_utc"]),
            -row["freeze_streak"],
            name_by_user.get(row["user_id"], ""),
        )
    )

    ranked = rows[:limit]
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
    return ranked


def compute_club_leaderboard(club_id: str, today: date, limit: int = 10) -> Dict[str, Any]:
    """
    Compute a mixed rolling 7-day leaderboard (ending `today`) across every
    promise actively shared with this club. Pure data — callers are
    responsible for any access-control checks (e.g. the webapp route
    verifying the requesting user is a member).

    Returns a plain dict; `members`/`promises` are lists of plain dicts too,
    matching the field names of `webapp.schemas.ClubLeaderboardMember` /
    `ClubLeaderboardPromiseSummary` so a caller can build those models with
    `Model(**item)` if needed.
    """
    window_start = today - timedelta(days=6)

    with get_db_session() as session:
        members = [
            dict(row)
            for row in session.execute(
                text("""
                    SELECT
                        cm.user_id,
                        u.first_name,
                        u.username,
                        u.avatar_path
                    FROM club_members cm
                    LEFT JOIN users u ON u.user_id = cm.user_id
                    WHERE cm.club_id = :club_id
                      AND cm.status = 'active'
                    ORDER BY cm.joined_at_utc ASC;
                """),
                {"club_id": club_id},
            ).mappings().fetchall()
        ]

        promises = [
            dict(row)
            for row in session.execute(
                text("""
                    SELECT
                        p.promise_uuid,
                        p.text AS promise_text,
                        CASE
                            WHEN pi.metric_type = 'count' THEN 'count'
                            ELSE 'hours'
                        END AS metric_type,
                        CASE
                            WHEN pi.metric_type = 'count'
                                THEN COALESCE(pi.target_value, 7.0)
                            ELSE COALESCE(pi.target_value, NULLIF(p.hours_per_week, 0), 1.0)
                        END AS target_value
                    FROM promise_club_shares pcs
                    JOIN promises p
                      ON p.promise_uuid = pcs.promise_uuid
                     AND p.is_deleted = 0
                    LEFT JOIN promise_instances pi
                      ON pi.promise_uuid = p.promise_uuid
                     AND pi.status = 'active'
                    WHERE pcs.club_id = :club_id
                    ORDER BY pcs.created_at_utc ASC;
                """),
                {"club_id": club_id},
            ).mappings().fetchall()
        ]

        action_rows = session.execute(
            text("""
                SELECT
                    a.user_id,
                    a.promise_uuid,
                    a.action_type,
                    COALESCE(a.time_spent_hours, 0.0) AS time_spent_hours,
                    a.score AS score,
                    DATE(a.at_utc::timestamptz) AS action_date,
                    a.at_utc AS at_utc
                FROM actions a
                JOIN club_members cm
                  ON cm.user_id = a.user_id
                 AND cm.club_id = :club_id
                 AND cm.status = 'active'
                JOIN promise_club_shares pcs
                  ON pcs.club_id = cm.club_id
                 AND pcs.promise_uuid = a.promise_uuid
                WHERE DATE(a.at_utc::timestamptz) >= :window_start
                  AND DATE(a.at_utc::timestamptz) <= :today
                  AND a.action_type IN ('club_checkin', 'checkin', 'log_time');
            """),
            {"club_id": club_id, "window_start": window_start, "today": today},
        ).mappings().fetchall()

    actions_by_member_promise: dict[tuple[str, str], dict] = defaultdict(
        lambda: {
            "activity_days": set(),
            "checkin_days": set(),
            "daily": defaultdict(lambda: {"checkins": 0, "duration_hours": 0.0, "score": None}),
            "duration_hours": 0.0,
            "checkin_count": 0,
            "last_activity_at_utc": None,
        }
    )
    for row in action_rows:
        key = (str(row["user_id"]), str(row["promise_uuid"]))
        stats = actions_by_member_promise[key]
        action_type = str(row["action_type"] or "")
        if action_type in ("club_checkin", "checkin"):
            action_date = _date_key(row["action_date"])
            stats["activity_days"].add(action_date)
            stats["checkin_days"].add(action_date)
            stats["daily"][action_date]["checkins"] += 1
            stats["checkin_count"] += 1
            if row["score"] is not None:
                # Non-binary scored check-in (e.g. a challenge daily quiz): the day's
                # score is the quiz result, not just "did you show up".
                stats["daily"][action_date]["score"] = float(row["score"])
        elif action_type == "log_time":
            hours = float(row["time_spent_hours"] or 0.0)
            if hours > 0:
                action_date = _date_key(row["action_date"])
                stats["duration_hours"] += hours
                stats["activity_days"].add(action_date)
                stats["daily"][action_date]["duration_hours"] += hours
        at_utc = str(row["at_utc"]) if row["at_utc"] else None
        if at_utc and (not stats["last_activity_at_utc"] or at_utc > stats["last_activity_at_utc"]):
            stats["last_activity_at_utc"] = at_utc

    all_members = _rank_club_leaderboard_members(
        members=members,
        promises=promises,
        actions_by_member_promise=actions_by_member_promise,
        today=today,
        limit=max(len(members), limit),
    )
    selected_members = all_members[:limit]
    average_score = (
        round(sum(member["score_percent"] for member in all_members) / len(all_members), 1)
        if all_members
        else 0.0
    )

    return {
        "window_start": window_start,
        "window_end": today,
        "member_count": len(members),
        "promise_count": len(promises),
        "average_score_percent": average_score,
        "promises": [
            {
                "promise_uuid": str(promise["promise_uuid"]),
                "promise_text": str(promise["promise_text"] or "Club promise"),
                "metric_type": str(promise["metric_type"] or "hours"),
                "target_value": float(promise["target_value"] or 1.0),
            }
            for promise in promises
        ],
        "members": selected_members,
    }


def resolve_avatar_data_uris(user_ids: List[str], root_dir: Optional[str] = None) -> Dict[str, str]:
    """
    Resolve public avatars to inline `data:` URIs for the bot's rendered
    leaderboard image.

    The webapp's own `<img src="/api/media/avatars/{user_id}">` requires
    Telegram auth (`get_current_user`), which a server-side Playwright
    render has no session for — that request would just 401. Read the
    files directly instead, applying the same visibility check and
    path-traversal guard as `webapp/routers/health.py::get_user_avatar`.
    """
    if not user_ids:
        return {}
    root = root_dir or os.getenv("ROOT_DIR") or os.getcwd()
    root_abs = os.path.abspath(root)

    with get_db_session() as session:
        rows = session.execute(
            text("""
                SELECT user_id, avatar_path, avatar_visibility
                FROM users
                WHERE user_id = ANY(:user_ids);
            """),
            {"user_ids": [str(u) for u in user_ids]},
        ).mappings().fetchall()

    data_uris: Dict[str, str] = {}
    for row in rows:
        avatar_path = row.get("avatar_path")
        visibility = row.get("avatar_visibility") or "public"
        if not avatar_path or visibility != "public":
            continue

        full_path = avatar_path if os.path.isabs(avatar_path) else os.path.join(root, avatar_path)
        full_path = os.path.normpath(full_path)
        if not os.path.abspath(full_path).startswith(root_abs):
            continue
        if not os.path.isfile(full_path):
            continue

        mime_type, _ = mimetypes.guess_type(full_path)
        try:
            with open(full_path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("ascii")
        except OSError:
            continue
        data_uris[str(row["user_id"])] = f"data:{mime_type or 'image/jpeg'};base64,{encoded}"

    return data_uris
