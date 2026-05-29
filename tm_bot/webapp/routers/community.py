"""
Community-related endpoints (suggestions, public promises, follows).
"""

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import List, Optional
import asyncio
import json
import os
import tempfile
import uuid

import httpx

from fastapi import APIRouter, HTTPException, Query, Depends, Request, UploadFile, File, Form
from sqlalchemy import text
from ..dependencies import get_current_user
from ..schemas import (
    AddClubPromiseRequest,
    ClubActionResponse,
    ClubContextIngestResponse,
    ClubLeaderboardBreakdown,
    ClubLeaderboardDailyActivity,
    ClubLeaderboardMember,
    ClubLeaderboardPromiseSummary,
    ClubLeaderboardResponse,
    ClubMemberSummary,
    CreateClubRequest,
    ClubsResponse,
    ClubSummary,
    CreateSuggestionRequest,
    PublicPromiseBadge,
    UpdateClubContextRequest,
    UpdateClubPromiseRequest,
    UpdateClubSettingsRequest,
)
from models.models import Promise
from repositories.clubs_repo import ClubsRepository, ensure_club_telegram_columns, get_club_columns
from repositories.settings_repo import SettingsRepository
from repositories.suggestions_repo import SuggestionsRepository
from repositories.templates_repo import TemplatesRepository
from repositories.promises_repo import PromisesRepository
from repositories.actions_repo import ActionsRepository
from services.reports import ReportsService
from db.postgres_db import get_db_session, resolve_promise_uuid, utc_now_iso, date_to_iso
from ..notifications import (
    send_club_pending_notification,
    send_club_telegram_setup_request,
    send_suggestion_notifications,
)
from utils.logger import get_logger

router = APIRouter(prefix="/api", tags=["community"])
logger = get_logger(__name__)


CLUB_CONTEXT_FIELDS = {"description", "club_goal", "vibe", "checkin_what_counts"}


def _date_key(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _calculate_freeze_streak(activity_dates: list[date], today: date, freeze_budget: int = 2) -> int:
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
) -> list[ClubLeaderboardMember]:
    rows: list[ClubLeaderboardMember] = []
    name_by_user: dict[str, str] = {}
    window_dates = [today - timedelta(days=offset) for offset in range(6, -1, -1)]

    for member in members:
        user_id = str(member["user_id"])
        name_by_user[user_id] = _display_name_key(member)
        breakdown: list[ClubLeaderboardBreakdown] = []
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

                if metric_type == "count":
                    day_score = 100.0 if day_checkins > 0 else 0.0
                else:
                    daily_target = max(target_value / 7.0, 0.25)
                    day_score = min(round((day_duration_hours / daily_target) * 100, 1), 100.0)

                totals = daily_totals[activity_date]
                totals["checkins"] += day_checkins
                totals["duration_hours"] += day_duration_hours
                totals["score_sum"] += day_score
                totals["score_count"] += 1

            breakdown.append(
                ClubLeaderboardBreakdown(
                    promise_uuid=promise_uuid,
                    promise_text=str(promise.get("promise_text") or "Club promise"),
                    metric_type=metric_type,
                    target_value=target_value,
                    achieved_value=round(achieved_value, 2),
                    active_days=active_days_count,
                    duration_hours=round(duration_hours, 2),
                    checkin_count=checkin_count,
                    progress_percent=progress_percent,
                )
            )

        score_percent = (
            round(sum(item.progress_percent for item in breakdown) / len(breakdown), 1)
            if breakdown
            else 0.0
        )
        daily_activity = [
            ClubLeaderboardDailyActivity(
                date=activity_date.isoformat(),
                active=totals["checkins"] > 0 or totals["duration_hours"] > 0,
                checkins=int(totals["checkins"]),
                duration_hours=round(float(totals["duration_hours"]), 2),
                score_percent=(
                    round(float(totals["score_sum"]) / int(totals["score_count"]), 1)
                    if int(totals["score_count"]) > 0
                    else 0.0
                ),
            )
            for activity_date, totals in daily_totals.items()
        ]
        rows.append(
            ClubLeaderboardMember(
                rank=0,
                user_id=user_id,
                first_name=str(member["first_name"]) if member.get("first_name") else None,
                username=str(member["username"]) if member.get("username") else None,
                avatar_path=str(member["avatar_path"]) if member.get("avatar_path") else None,
                score_percent=score_percent,
                active_days=len(activity_dates),
                duration_hours=round(total_duration_hours, 2),
                checkin_count=total_checkins,
                freeze_streak=_calculate_freeze_streak(list(activity_dates), today),
                last_activity_at_utc=last_activity_at_utc,
                daily_activity=daily_activity,
                breakdown=breakdown,
            )
        )

    rows.sort(
        key=lambda row: (
            -row.score_percent,
            _sort_timestamp_desc(row.last_activity_at_utc),
            -row.freeze_streak,
            name_by_user.get(row.user_id, ""),
        )
    )

    ranked = rows[:limit]
    for index, row in enumerate(ranked, start=1):
        row.rank = index
    return ranked


def _generate_club_promise_id(user_id: int) -> str:
    promises = PromisesRepository().list_promises(user_id)
    numbers = []
    for promise in promises:
        pid = (promise.id or "").upper()
        if not pid.startswith("C"):
            continue
        try:
            numbers.append(int(pid[1:]))
        except ValueError:
            continue
    return f"C{(max(numbers) if numbers else 0) + 1:02d}"


def _ensure_user_exists(user_id: int) -> None:
    settings_repo = SettingsRepository()
    settings = settings_repo.get_settings(user_id)
    settings_repo.save_settings(settings)


def _create_club_promise(
    user_id: int,
    club_id: str,
    club_name: str,
    promise_text: str,
    target_count_per_week: float,
) -> tuple[str, str]:
    user = str(user_id)
    promise_id = _generate_club_promise_id(user_id)
    now = utc_now_iso()
    today = datetime.now().date()

    template_id = TemplatesRepository().create_template({
        "title": promise_text.strip(),
        "description": f"Shared promise for {club_name}",
        "category": "club",
        "target_value": target_count_per_week,
        "metric_type": "count",
        "emoji": None,
        "is_active": False,
        "created_by_user_id": user,
    })

    promise = Promise(
        user_id=user,
        id=promise_id,
        text=promise_text.strip(),
        hours_per_week=0.0,
        recurring=True,
        start_date=today,
        visibility="clubs",
        description=f"Shared with club: {club_name}",
    )
    PromisesRepository().upsert_promise(user_id, promise)

    with get_db_session() as session:
        promise_uuid = resolve_promise_uuid(session, user, promise_id)
        if not promise_uuid:
            raise RuntimeError("Failed to resolve club promise")

        session.execute(
            text("""
                INSERT INTO promise_instances (
                    instance_id, user_id, template_id, promise_uuid, status,
                    metric_type, target_value, estimated_hours_per_unit,
                    start_date, end_date, created_at_utc, updated_at_utc
                ) VALUES (
                    :instance_id, :user_id, :template_id, :promise_uuid, 'active',
                    'count', :target_value, 1.0,
                    :start_date, NULL, :now, :now
                );
            """),
            {
                "instance_id": str(uuid.uuid4()),
                "user_id": user,
                "template_id": template_id,
                "promise_uuid": promise_uuid,
                "target_value": float(target_count_per_week),
                "start_date": date_to_iso(today),
                "now": now,
            },
        )

    ClubsRepository().share_promise_to_club(promise_uuid, club_id)
    return promise_id, promise_uuid


def _list_user_clubs(user_id: int) -> List[ClubSummary]:
    user = str(user_id)
    with get_db_session() as session:
        ensure_club_telegram_columns(session)
        club_columns = get_club_columns(session)

        telegram_status_select = (
            "c.telegram_status"
            if "telegram_status" in club_columns
            else "'not_connected' AS telegram_status"
        )
        telegram_invite_select = (
            "c.telegram_invite_link"
            if "telegram_invite_link" in club_columns
            else "CAST(NULL AS TEXT) AS telegram_invite_link"
        )

        rows = session.execute(
            text(f"""
                SELECT DISTINCT ON (c.club_id)
                    c.club_id,
                    c.name,
                    c.visibility,
                    {telegram_status_select},
                    {telegram_invite_select},
                    cm.role,
                    COALESCE(member_counts.member_count, 0) AS member_count,
                    COALESCE(promise_counts.promise_count, 0) AS promise_count,
                    p.current_id AS promise_id,
                    p.promise_uuid AS promise_uuid,
                    p.text AS promise_text,
                    pi.target_value AS target_count_per_week,
                    c.reminder_time,
                    c.language,
                    c.description,
                    c.club_goal,
                    c.vibe,
                    c.checkin_what_counts
                FROM clubs c
                INNER JOIN club_members cm
                    ON cm.club_id = c.club_id
                   AND cm.user_id = :user_id
                   AND cm.status = 'active'
                LEFT JOIN (
                    SELECT club_id, COUNT(*) AS member_count
                    FROM club_members
                    WHERE status = 'active'
                    GROUP BY club_id
                ) member_counts ON member_counts.club_id = c.club_id
                LEFT JOIN (
                    SELECT pcs.club_id, COUNT(*) AS promise_count
                    FROM promise_club_shares pcs
                    JOIN promises p
                      ON p.promise_uuid = pcs.promise_uuid
                     AND p.is_deleted = 0
                    GROUP BY pcs.club_id
                ) promise_counts ON promise_counts.club_id = c.club_id
                LEFT JOIN promise_club_shares pcs ON pcs.club_id = c.club_id
                LEFT JOIN promises p
                    ON p.promise_uuid = pcs.promise_uuid
                   AND p.is_deleted = 0
                LEFT JOIN promise_instances pi
                    ON pi.promise_uuid = p.promise_uuid
                   AND pi.user_id = p.user_id
                   AND pi.status = 'active'
                WHERE COALESCE(c.status, 'active') = 'active'
                ORDER BY c.club_id, pcs.created_at_utc ASC;
            """),
            {"user_id": user},
        ).mappings().fetchall()

        club_ids = [str(row["club_id"]) for row in rows]
        member_rows = []
        if club_ids:
            member_rows = session.execute(
                text("""
                    SELECT
                        cm.club_id,
                        cm.user_id,
                        u.first_name,
                        u.username,
                        u.avatar_path
                    FROM club_members cm
                    LEFT JOIN users u ON u.user_id = cm.user_id
                    WHERE cm.status = 'active'
                      AND cm.club_id = ANY(:club_ids)
                    ORDER BY cm.joined_at_utc ASC;
                """),
                {"club_ids": club_ids},
            ).mappings().fetchall()

    members_by_club: dict[str, List[ClubMemberSummary]] = {}
    for member in member_rows:
        club_id = str(member["club_id"])
        members_by_club.setdefault(club_id, []).append(
            ClubMemberSummary(
                user_id=str(member["user_id"]),
                first_name=str(member["first_name"]) if member["first_name"] else None,
                username=str(member["username"]) if member["username"] else None,
                avatar_path=str(member["avatar_path"]) if member["avatar_path"] else None,
            )
        )

    return [
        ClubSummary(
            club_id=str(row["club_id"]),
            name=str(row["name"]),
            visibility=str(row["visibility"] or "private"),
            role=str(row["role"] or "member"),
            member_count=int(row["member_count"] or 0),
            members=members_by_club.get(str(row["club_id"]), []),
            telegram_status=str(row["telegram_status"] or "not_connected"),
            telegram_invite_link=str(row["telegram_invite_link"]) if row["telegram_invite_link"] else None,
            promise_id=str(row["promise_id"]) if row["promise_id"] else None,
            promise_uuid=str(row["promise_uuid"]) if row["promise_uuid"] else None,
            promise_text=str(row["promise_text"]) if row["promise_text"] else None,
            promise_count=int(row["promise_count"] or 0),
            target_count_per_week=float(row["target_count_per_week"]) if row["target_count_per_week"] is not None else None,
            reminder_time=str(row["reminder_time"]) if row["reminder_time"] else None,
            language=str(row["language"]) if row["language"] else None,
            description=str(row["description"]) if row["description"] else None,
            club_goal=str(row["club_goal"]) if row["club_goal"] else None,
            vibe=str(row["vibe"]) if row["vibe"] else None,
            checkin_what_counts=str(row["checkin_what_counts"]) if row["checkin_what_counts"] else None,
        )
        for row in rows
    ]


async def _is_club_admin(user_id: int, club: dict, bot_token: str) -> bool:
    """Return True if user is the club owner, or a Telegram group admin."""
    if str(club.get("owner_user_id")) == str(user_id):
        return True
    telegram_chat_id = club.get("telegram_chat_id")
    if not telegram_chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getChatAdministrators"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params={"chat_id": telegram_chat_id})
        if resp.status_code == 200:
            admins = resp.json().get("result", [])
            admin_ids = {str(m["user"]["id"]) for m in admins}
            return str(user_id) in admin_ids
    except Exception:
        pass
    return False


def _clean_context_value(value: object, max_length: int) -> str:
    text_value = "" if value is None else str(value).strip()
    return text_value[:max_length]


def _first_matching_sentence(source: str, needles: tuple[str, ...]) -> str:
    import re

    for sentence in re.split(r"(?<=[.!?؟])\s+|\n+", source):
        candidate = sentence.strip(" -•\t")
        if not candidate:
            continue
        lowered = candidate.lower()
        if any(needle in lowered for needle in needles):
            return candidate
    return ""


def _heuristic_club_context_extract(
    *,
    source_text: str,
    club: dict,
    current: dict,
) -> tuple[dict, list[str]]:
    compact = " ".join(source_text.split())
    promise_text = str(club.get("promise_text") or "").strip()
    name = str(club.get("name") or "").strip()

    description = _first_matching_sentence(compact, ("for ", "members", "people", "group", "club", "collective"))
    if not description:
        description = compact[:420]

    goal = _first_matching_sentence(compact, ("goal", "aim", "target", "purpose", "help", "build", "become", "create"))
    if not goal and promise_text:
        goal = f"Help members follow through on: {promise_text}"
    elif not goal and name:
        goal = f"Help members stay accountable to {name}."

    vibe = _first_matching_sentence(compact, ("vibe", "tone", "strict", "gentle", "playful", "warm", "direct", "friendly"))
    checkin = _first_matching_sentence(compact, ("check-in", "checkin", "counts", "done", "report", "valid", "complete"))
    if not checkin and promise_text:
        checkin = f"A check-in counts when a member reports progress on: {promise_text}"

    extracted = {
        "description": _clean_context_value(description or current.get("description"), 1000),
        "club_goal": _clean_context_value(goal or current.get("club_goal"), 1500),
        "vibe": _clean_context_value(vibe or current.get("vibe"), 500),
        "checkin_what_counts": _clean_context_value(checkin or current.get("checkin_what_counts"), 700),
    }
    followups = []
    if not extracted["checkin_what_counts"]:
        followups.append("What should count as a valid check-in?")
    if not extracted["vibe"]:
        followups.append("What tone should Xaana use with this group?")
    return extracted, followups


def _parse_context_json(content: str) -> dict:
    text_value = str(content or "").strip()
    if text_value.startswith("```"):
        text_value = text_value.strip("`")
        if text_value.lower().startswith("json"):
            text_value = text_value[4:].strip()
    start = text_value.find("{")
    end = text_value.rfind("}")
    if start >= 0 and end > start:
        text_value = text_value[start:end + 1]
    return json.loads(text_value)


def _llm_club_context_extract(
    *,
    source_text: str,
    club: dict,
    current: dict,
) -> tuple[Optional[dict], list[str]]:
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_openai import ChatOpenAI
        from llms.llm_env_utils import load_llm_env

        cfg = load_llm_env()
        chat_model = None
        if cfg.get("GCP_PROJECT_ID"):
            chat_model = ChatGoogleGenerativeAI(
                model=cfg.get("LLM_RESPONDER_MODEL") or cfg.get("GCP_GEMINI_MODEL"),
                project=cfg["GCP_PROJECT_ID"],
                location=cfg.get("GCP_LLM_LOCATION", cfg["GCP_LOCATION"]),
                temperature=0.2,
            )
        elif cfg.get("OPENAI_API_KEY"):
            chat_model = ChatOpenAI(
                openai_api_key=cfg["OPENAI_API_KEY"],
                model=cfg.get("LLM_OPENAI_RESPONDER_MODEL") or "gpt-4o-mini",
                temperature=0.2,
            )
        if chat_model is None:
            return None, []

        prompt_payload = {
            "club": {
                "name": club.get("name"),
                "promise_text": club.get("promise_text"),
                "target_count_per_week": club.get("target_count_per_week"),
            },
            "current_context": current,
            "owner_material": source_text[:12000],
        }
        messages = [
            SystemMessage(content=(
                "You extract concise club context for Xaana, an accountability coach in Telegram groups. "
                "Return only JSON with keys: description, club_goal, vibe, checkin_what_counts, follow_up_questions. "
                "Keep each field short, practical, and useful for future group replies. "
                "If source material is ambiguous, preserve existing context and ask at most 3 follow-up questions."
            )),
            HumanMessage(content=json.dumps(prompt_payload, ensure_ascii=False)),
        ]
        response = chat_model.invoke(messages)
        payload = _parse_context_json(getattr(response, "content", response))
        extracted = {
            "description": _clean_context_value(payload.get("description") or current.get("description"), 1000),
            "club_goal": _clean_context_value(payload.get("club_goal") or current.get("club_goal"), 1500),
            "vibe": _clean_context_value(payload.get("vibe") or current.get("vibe"), 500),
            "checkin_what_counts": _clean_context_value(payload.get("checkin_what_counts") or current.get("checkin_what_counts"), 700),
        }
        questions = payload.get("follow_up_questions") or []
        followups = [str(item).strip()[:180] for item in questions if str(item).strip()][:3]
        return extracted, followups
    except Exception as exc:
        logger.info("Club context LLM extraction unavailable, using heuristic fallback: %s", exc)
        return None, []


async def _extract_uploaded_image_text(files: List[UploadFile]) -> tuple[list[str], Optional[str]]:
    if not files:
        return [], None
    try:
        from services.image_service import ImageService
        image_service = ImageService()
    except Exception as exc:
        return [], f"Image extraction unavailable: {exc}"

    extracted: list[str] = []
    for upload in files[:4]:
        content_type = (upload.content_type or "").lower()
        if not content_type.startswith("image/"):
            continue
        suffix = os.path.splitext(upload.filename or "")[1] or ".jpg"
        tmp_path = ""
        try:
            data = await upload.read()
            if len(data) > 8 * 1024 * 1024:
                extracted.append(f"Image {upload.filename or ''} skipped: file is larger than 8MB.")
                continue
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(data)
                tmp_path = tmp.name
            analysis = await asyncio.to_thread(image_service.parse_image, tmp_path)
            text_value = image_service.extract_text_for_processing(analysis)
            if text_value:
                extracted.append(f"Image {upload.filename or 'upload'}:\n{text_value}")
        except Exception as exc:
            extracted.append(f"Image {upload.filename or 'upload'} could not be read: {exc}")
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
    return extracted, None


@router.get("/clubs", response_model=ClubsResponse)
async def list_my_clubs(user_id: int = Depends(get_current_user)):
    """List clubs where the current user is an active member."""
    try:
        clubs = _list_user_clubs(user_id)
        return ClubsResponse(clubs=clubs, total=len(clubs))
    except Exception as e:
        logger.exception(f"Error listing clubs for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load clubs: {str(e)}")


@router.get("/clubs/{club_id}/leaderboard", response_model=ClubLeaderboardResponse)
async def get_club_leaderboard(
    club_id: str,
    window: str = Query(default="rolling_7d", pattern="^rolling_7d$"),
    limit: int = Query(default=10, ge=1, le=10),
    user_id: int = Depends(get_current_user),
):
    """Return a mixed rolling 7-day leaderboard across active shared club promises."""
    user = str(user_id)
    today = datetime.utcnow().date()
    window_start = today - timedelta(days=6)

    try:
        with get_db_session() as session:
            member_check = session.execute(
                text("""
                    SELECT 1
                    FROM club_members cm
                    JOIN clubs c ON c.club_id = cm.club_id
                    WHERE cm.club_id = :club_id
                      AND cm.user_id = :user_id
                      AND cm.status = 'active'
                      AND COALESCE(c.status, 'active') = 'active'
                    LIMIT 1;
                """),
                {"club_id": club_id, "user_id": user},
            ).fetchone()
            if not member_check:
                raise HTTPException(status_code=404, detail="Club not found")

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
                "daily": defaultdict(lambda: {"checkins": 0, "duration_hours": 0.0}),
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
            round(sum(member.score_percent for member in all_members) / len(all_members), 1)
            if all_members
            else 0.0
        )

        return ClubLeaderboardResponse(
            club_id=club_id,
            window=window,
            window_start=window_start.isoformat(),
            window_end=today.isoformat(),
            member_count=len(members),
            promise_count=len(promises),
            average_score_percent=average_score,
            promises=[
                ClubLeaderboardPromiseSummary(
                    promise_uuid=str(promise["promise_uuid"]),
                    promise_text=str(promise["promise_text"] or "Club promise"),
                    metric_type=str(promise["metric_type"] or "hours"),
                    target_value=float(promise["target_value"] or 1.0),
                )
                for promise in promises
            ],
            members=selected_members,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error loading club leaderboard for {club_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load club leaderboard: {str(e)}")


@router.post("/clubs", response_model=ClubSummary)
async def create_club(
    request: Request,
    club_request: CreateClubRequest,
    user_id: int = Depends(get_current_user),
):
    """Create a minimal Xaana club with one shared count-based promise."""
    try:
        _ensure_user_exists(user_id)
        name = club_request.name.strip()
        promise_text = club_request.promise_text.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Club name is required")
        if not promise_text:
            raise HTTPException(status_code=400, detail="Shared promise is required")

        clubs_repo = ClubsRepository()
        club_id = clubs_repo.create_club(
            owner_user_id=user_id,
            name=name,
            description=None,
            visibility=club_request.visibility,
        )
        _create_club_promise(
            user_id=user_id,
            club_id=club_id,
            club_name=name,
            promise_text=promise_text,
            target_count_per_week=club_request.target_count_per_week,
        )
        asyncio.create_task(
            send_club_telegram_setup_request(
                bot_token=request.app.state.bot_token,
                club_id=club_id,
                club_name=name,
                creator_user_id=user_id,
                promise_text=promise_text,
                miniapp_url=os.getenv("MINIAPP_URL", "https://xaana.club"),
            )
        )
        asyncio.create_task(
            send_club_pending_notification(
                bot_token=request.app.state.bot_token,
                user_id=user_id,
                club_id=club_id,
                club_name=name,
            )
        )
        clubs = _list_user_clubs(user_id)
        created = next((club for club in clubs if club.club_id == club_id), None)
        if not created:
            raise RuntimeError("Club was created but could not be loaded")
        return created
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error creating club for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create club: {str(e)}")


@router.put("/clubs/{club_id}", response_model=ClubSummary)
async def update_club_settings(
    request: Request,
    club_id: str,
    body: UpdateClubSettingsRequest,
    user_id: int = Depends(get_current_user),
):
    """Update club settings (reminder_time, language). Only club admins may call this."""
    try:
        clubs_repo = ClubsRepository()
        club = clubs_repo.get_club(club_id)
        if not club or str(club.get("status") or "active") != "active":
            raise HTTPException(status_code=404, detail="Club not found")

        if not await _is_club_admin(user_id, club, request.app.state.bot_token):
            raise HTTPException(status_code=403, detail="Only club admins can update club settings")

        updates: dict = {}
        if body.reminder_time is not None:
            updates["reminder_time"] = body.reminder_time
        if body.language is not None:
            updates["language"] = body.language

        if updates:
            now = utc_now_iso()
            set_clause = ", ".join(f"{k} = :{k}" for k in updates)
            updates["club_id"] = club_id
            updates["updated_at_utc"] = now
            with get_db_session() as session:
                session.execute(
                    text(f"UPDATE clubs SET {set_clause}, updated_at_utc = :updated_at_utc WHERE club_id = :club_id;"),
                    updates,
                )

        clubs = _list_user_clubs(user_id)
        updated = next((c for c in clubs if c.club_id == club_id), None)
        if not updated:
            raise RuntimeError("Club updated but could not be reloaded")
        return updated
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating club settings {club_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update club: {str(e)}")


@router.put("/clubs/{club_id}/context", response_model=ClubSummary)
async def update_club_context(
    request: Request,
    club_id: str,
    body: UpdateClubContextRequest,
    user_id: int = Depends(get_current_user),
):
    """Update bot-facing club context. Only club owners or Telegram group admins may call this."""
    fields_set = getattr(body, "model_fields_set", None) or getattr(body, "__fields_set__", set())
    provided = CLUB_CONTEXT_FIELDS.intersection(fields_set)
    if not provided:
        raise HTTPException(status_code=400, detail="Provide at least one club context field")

    try:
        clubs_repo = ClubsRepository()
        club = clubs_repo.get_club(club_id)
        if not club or str(club.get("status") or "active") != "active":
            raise HTTPException(status_code=404, detail="Club not found")

        if not await _is_club_admin(user_id, club, request.app.state.bot_token):
            raise HTTPException(status_code=403, detail="Only club admins can update club context")

        values: dict[str, str] = {}
        for field_name in CLUB_CONTEXT_FIELDS:
            if field_name in provided:
                raw_value = getattr(body, field_name)
                values[field_name] = "" if raw_value is None else str(raw_value).strip()

        clubs_repo.update_club_context(
            club_id=club_id,
            description=values.get("description") if "description" in values else None,
            club_goal=values.get("club_goal") if "club_goal" in values else None,
            vibe=values.get("vibe") if "vibe" in values else None,
            checkin_what_counts=values.get("checkin_what_counts") if "checkin_what_counts" in values else None,
        )

        if "club_goal" in values:
            try:
                from memory.club_memory import club_memory_upsert_fact
                root_dir = getattr(request.app.state, "root_dir", None) or os.getenv("ROOT_DIR") or os.getcwd()
                club_memory_upsert_fact(root_dir, club_id, "club_goal", values["club_goal"])
            except Exception as memory_error:
                logger.warning("Failed to sync club_goal memory for club %s: %s", club_id, memory_error)

        clubs = _list_user_clubs(user_id)
        updated = next((c for c in clubs if c.club_id == club_id), None)
        if not updated:
            raise RuntimeError("Club context updated but could not be reloaded")
        return updated
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating club context {club_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update club context: {str(e)}")


@router.post("/clubs/{club_id}/context/ingest", response_model=ClubContextIngestResponse)
async def ingest_club_context(
    request: Request,
    club_id: str,
    notes: str = Form(default=""),
    files: Optional[List[UploadFile]] = File(default=None),
    user_id: int = Depends(get_current_user),
):
    """Extract bot-facing club context from natural owner notes and optional images."""
    notes = (notes or "").strip()
    uploads = files or []
    if not notes and not uploads:
        raise HTTPException(status_code=400, detail="Add notes or images first")

    try:
        clubs_repo = ClubsRepository()
        club = clubs_repo.get_club(club_id)
        if not club or str(club.get("status") or "active") != "active":
            raise HTTPException(status_code=404, detail="Club not found")

        if not await _is_club_admin(user_id, club, request.app.state.bot_token):
            raise HTTPException(status_code=403, detail="Only club admins can update club context")

        current = {
            "description": str(club.get("description") or ""),
            "club_goal": str(club.get("club_goal") or ""),
            "vibe": str(club.get("vibe") or ""),
            "checkin_what_counts": str(club.get("checkin_what_counts") or ""),
        }
        image_parts, image_error = await _extract_uploaded_image_text(uploads)
        source_parts = []
        if notes:
            source_parts.append(f"Owner notes:\n{notes}")
        source_parts.extend(image_parts)
        source_text = "\n\n".join(source_parts).strip()
        if not source_text:
            raise HTTPException(status_code=400, detail=image_error or "No readable context found")

        extracted, followups = _llm_club_context_extract(
            source_text=source_text,
            club=club,
            current=current,
        )
        used_llm = extracted is not None
        if extracted is None:
            extracted, followups = _heuristic_club_context_extract(
                source_text=source_text,
                club=club,
                current=current,
            )

        clubs_repo.update_club_context(
            club_id=club_id,
            description=extracted.get("description"),
            club_goal=extracted.get("club_goal"),
            vibe=extracted.get("vibe"),
            checkin_what_counts=extracted.get("checkin_what_counts"),
        )

        try:
            from memory.club_memory import club_memory_upsert_fact, club_memory_write
            root_dir = getattr(request.app.state, "root_dir", None) or os.getenv("ROOT_DIR") or os.getcwd()
            if extracted.get("club_goal") is not None:
                club_memory_upsert_fact(root_dir, club_id, "club_goal", extracted["club_goal"])
            club_memory_write(f"Owner-provided context source:\n{source_text[:4000]}", root_dir, club_id)
        except Exception as memory_error:
            logger.warning("Failed to sync ingested club context memory for club %s: %s", club_id, memory_error)

        clubs = _list_user_clubs(user_id)
        updated = next((c for c in clubs if c.club_id == club_id), None)
        if not updated:
            raise RuntimeError("Club context ingested but could not be reloaded")
        return ClubContextIngestResponse(
            club=updated,
            extracted=UpdateClubContextRequest(**extracted),
            follow_up_questions=followups,
            used_llm=used_llm,
            image_count=len(uploads),
            image_error=image_error,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error ingesting club context {club_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to ingest club context: {str(e)}")


@router.post("/clubs/{club_id}/promises", response_model=ClubSummary)
async def add_club_promise(
    request: Request,
    club_id: str,
    body: AddClubPromiseRequest,
    user_id: int = Depends(get_current_user),
):
    """Add a club-level promise. Only the club owner or a Telegram group admin may do this."""
    try:
        clubs_repo = ClubsRepository()
        club = clubs_repo.get_club(club_id)
        if not club or str(club.get("status") or "active") != "active":
            raise HTTPException(status_code=404, detail="Club not found")

        if not await _is_club_admin(user_id, club, request.app.state.bot_token):
            raise HTTPException(status_code=403, detail="Only club admins can define club promises")

        promise_text = body.promise_text.strip()
        if not promise_text:
            raise HTTPException(status_code=400, detail="Promise text is required")

        _ensure_user_exists(user_id)
        _create_club_promise(
            user_id=user_id,
            club_id=club_id,
            club_name=str(club["name"]),
            promise_text=promise_text,
            target_count_per_week=body.target_count_per_week,
        )

        clubs = _list_user_clubs(user_id)
        updated = next((c for c in clubs if c.club_id == club_id), None)
        if not updated:
            raise RuntimeError("Club promise created but club could not be reloaded")
        return updated
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error adding promise to club {club_id} for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add club promise: {str(e)}")


@router.put("/clubs/{club_id}/promises/{promise_uuid}", response_model=ClubSummary)
async def update_club_promise(
    request: Request,
    club_id: str,
    promise_uuid: str,
    body: UpdateClubPromiseRequest,
    user_id: int = Depends(get_current_user),
):
    """Edit a club-level promise. Only the club owner or a Telegram group admin may do this."""
    try:
        clubs_repo = ClubsRepository()
        club = clubs_repo.get_club(club_id)
        if not club or str(club.get("status") or "active") != "active":
            raise HTTPException(status_code=404, detail="Club not found")

        if not await _is_club_admin(user_id, club, request.app.state.bot_token):
            raise HTTPException(status_code=403, detail="Only club admins can edit club promises")

        now = utc_now_iso()
        with get_db_session() as session:
            # Verify the promise is actually shared to this club
            shared = session.execute(
                text("SELECT 1 FROM promise_club_shares WHERE promise_uuid = :uuid AND club_id = :club_id LIMIT 1;"),
                {"uuid": promise_uuid, "club_id": club_id},
            ).fetchone()
            if not shared:
                raise HTTPException(status_code=404, detail="Promise not found in this club")

            if body.promise_text is not None:
                session.execute(
                    text("UPDATE promises SET text = :text, updated_at_utc = :now WHERE promise_uuid = :uuid;"),
                    {"text": body.promise_text.strip(), "now": now, "uuid": promise_uuid},
                )
            if body.target_count_per_week is not None:
                session.execute(
                    text("UPDATE promise_instances SET target_value = :val, updated_at_utc = :now WHERE promise_uuid = :uuid AND status = 'active';"),
                    {"val": float(body.target_count_per_week), "now": now, "uuid": promise_uuid},
                )

        clubs = _list_user_clubs(user_id)
        updated = next((c for c in clubs if c.club_id == club_id), None)
        if not updated:
            raise RuntimeError("Club promise updated but club could not be reloaded")
        return updated
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating promise {promise_uuid} in club {club_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update club promise: {str(e)}")


@router.delete("/clubs/{club_id}/promises/{promise_uuid}", response_model=ClubActionResponse)
async def delete_club_promise(
    request: Request,
    club_id: str,
    promise_uuid: str,
    user_id: int = Depends(get_current_user),
):
    """Delete a club-level promise. Only the club owner or a Telegram group admin may do this."""
    try:
        clubs_repo = ClubsRepository()
        club = clubs_repo.get_club(club_id)
        if not club or str(club.get("status") or "active") != "active":
            raise HTTPException(status_code=404, detail="Club not found")

        if not await _is_club_admin(user_id, club, request.app.state.bot_token):
            raise HTTPException(status_code=403, detail="Only club admins can delete club promises")

        now = utc_now_iso()
        with get_db_session() as session:
            shared = session.execute(
                text("SELECT 1 FROM promise_club_shares WHERE promise_uuid = :uuid AND club_id = :club_id LIMIT 1;"),
                {"uuid": promise_uuid, "club_id": club_id},
            ).fetchone()
            if not shared:
                raise HTTPException(status_code=404, detail="Promise not found in this club")

            session.execute(
                text("DELETE FROM promise_club_shares WHERE promise_uuid = :uuid AND club_id = :club_id;"),
                {"uuid": promise_uuid, "club_id": club_id},
            )
            session.execute(
                text("UPDATE promises SET is_deleted = 1, updated_at_utc = :now WHERE promise_uuid = :uuid;"),
                {"now": now, "uuid": promise_uuid},
            )

        return ClubActionResponse(status="deleted", club_id=club_id, message="Club promise deleted.")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error deleting promise {promise_uuid} from club {club_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete club promise: {str(e)}")


@router.post("/clubs/{club_id}/sync-description", response_model=ClubActionResponse)
async def sync_club_description(
    request: Request,
    club_id: str,
    user_id: int = Depends(get_current_user),
):
    """Push current club promise + reminder as the Telegram group description."""
    try:
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        club = ClubsRepository().get_club(club_id)
        if not club:
            raise HTTPException(status_code=404, detail="Club not found")

        if not await _is_club_admin(user_id, club, bot_token):
            raise HTTPException(status_code=403, detail="Only club admins can update the group description")

        chat_id = club.get("telegram_chat_id")
        if not chat_id:
            raise HTTPException(status_code=400, detail="No Telegram group connected to this club")

        # Build description
        parts = []
        promise_text = club.get("promise_text") or ""
        if not promise_text:
            # Fetch from promise_club_shares
            with get_db_session() as session:
                row = session.execute(
                    text("""
                        SELECT p.text, pi.target_value
                        FROM promise_club_shares pcs
                        JOIN promises p ON p.promise_uuid = pcs.promise_uuid AND p.is_deleted = 0
                        LEFT JOIN promise_instances pi ON pi.promise_uuid = p.promise_uuid AND pi.status = 'active'
                        WHERE pcs.club_id = :club_id
                        LIMIT 1
                    """),
                    {"club_id": club_id},
                ).fetchone()
                if row:
                    promise_text = row["text"] or ""
                    target = row["target_value"]
                    if promise_text:
                        parts.append(f"{promise_text}{f' · {int(target)}×/week' if target else ''}")
        else:
            parts.append(promise_text)

        reminder = club.get("reminder_time") or "21:00"
        parts.append(f"Reminder: {reminder}")
        description = " | ".join(parts)

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{bot_token}/setChatDescription",
                json={"chat_id": chat_id, "description": description},
                timeout=10,
            )
        if not resp.is_success or not resp.json().get("ok"):
            detail = resp.json().get("description", "Failed to update group description")
            raise HTTPException(status_code=502, detail=detail)

        return ClubActionResponse(status="updated", club_id=club_id, message="Group description updated.")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error syncing description for club {club_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/clubs/{club_id}", response_model=ClubActionResponse)
async def remove_my_club(
    club_id: str,
    user_id: int = Depends(get_current_user),
):
    """Cancel a pending owner-created club, or leave a club as a non-owner."""
    try:
        clubs_repo = ClubsRepository()
        club = clubs_repo.get_club(club_id)
        if not club or str(club.get("status") or "active") != "active":
            raise HTTPException(status_code=404, detail="Club not found")

        with get_db_session() as session:
            member_row = session.execute(
                text("""
                    SELECT role
                    FROM club_members
                    WHERE club_id = :club_id
                      AND user_id = :user_id
                      AND status = 'active'
                    LIMIT 1;
                """),
                {"club_id": club_id, "user_id": str(user_id)},
            ).mappings().fetchone()

        if not member_row:
            raise HTTPException(status_code=404, detail="Club not found")

        if str(club.get("owner_user_id")) == str(user_id):
            if str(club.get("telegram_status") or "") != "pending_admin_setup":
                raise HTTPException(status_code=409, detail="Active clubs cannot be cancelled yet.")
            if not clubs_repo.cancel_pending_club(club_id, user_id):
                raise HTTPException(status_code=409, detail="Club could not be cancelled.")
            return ClubActionResponse(status="cancelled", club_id=club_id, message="Club cancelled.")

        if not clubs_repo.remove_member(club_id, user_id):
            raise HTTPException(status_code=409, detail="Club could not be left.")
        return ClubActionResponse(status="left", club_id=club_id, message="You left the club.")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error removing club {club_id} for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update club: {str(e)}")


@router.post("/suggestions")
async def create_suggestion(
    request: Request,
    suggestion_request: CreateSuggestionRequest,
    user_id: int = Depends(get_current_user)
):
    """Create a promise suggestion for another user."""
    try:
        # Validate: must have either template_id or freeform_text
        if not suggestion_request.template_id and not suggestion_request.freeform_text:
            raise HTTPException(status_code=400, detail="Must provide either template_id or freeform_text")
        
        # Can't suggest to yourself
        if str(user_id) == str(suggestion_request.to_user_id):
            raise HTTPException(status_code=400, detail="Cannot suggest a promise to yourself")
        
        suggestions_repo = SuggestionsRepository()
        suggestion_id = suggestions_repo.create_suggestion(
            from_user_id=str(user_id),
            to_user_id=str(suggestion_request.to_user_id),
            template_id=suggestion_request.template_id,
            freeform_text=suggestion_request.freeform_text,
            message=suggestion_request.message
        )
        
        logger.info(f"User {user_id} created suggestion {suggestion_id} for user {suggestion_request.to_user_id}")
        
        # Get template title if template-based suggestion
        template_title = None
        if suggestion_request.template_id:
            templates_repo = TemplatesRepository()
            template = templates_repo.get_template(suggestion_request.template_id)
            if template:
                template_title = template.get("title")
        
        # Send Telegram notifications to both sender and receiver
        asyncio.create_task(
            send_suggestion_notifications(
                bot_token=request.app.state.bot_token,
                sender_id=user_id,
                receiver_id=int(suggestion_request.to_user_id),
                suggestion_id=suggestion_id,
                template_title=template_title,
                freeform_text=suggestion_request.freeform_text,
                message=suggestion_request.message,
            )
        )
        
        return {"status": "success", "suggestion_id": suggestion_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error creating suggestion: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create suggestion: {str(e)}")


@router.get("/suggestions/pending")
async def get_pending_suggestions(
    request: Request,
    user_id: int = Depends(get_current_user)
):
    """Get pending suggestions sent to the current user."""
    try:
        suggestions_repo = SuggestionsRepository()
        suggestions = suggestions_repo.get_pending_suggestions_for_user(str(user_id))
        
        return {"suggestions": suggestions}
    except Exception as e:
        logger.exception(f"Error getting pending suggestions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get suggestions: {str(e)}")


@router.put("/suggestions/{suggestion_id}/respond")
async def respond_to_suggestion(
    request: Request,
    suggestion_id: str,
    response: str = Query(..., regex="^(accept|decline)$"),
    user_id: int = Depends(get_current_user)
):
    """Accept or decline a suggestion."""
    try:
        suggestions_repo = SuggestionsRepository()
        
        new_status = "accepted" if response == "accept" else "declined"
        success = suggestions_repo.update_suggestion_status(
            suggestion_id=suggestion_id,
            new_status=new_status,
            user_id=str(user_id)
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Suggestion not found or not authorized")
        
        logger.info(f"User {user_id} {response}ed suggestion {suggestion_id}")
        return {"status": "success", "new_status": new_status}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error responding to suggestion: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to respond to suggestion: {str(e)}")


@router.get("/users/{user_id}/public-promises", response_model=List[PublicPromiseBadge])
async def get_public_promises(
    request: Request,
    user_id: int,
    current_user_id: int = Depends(get_current_user),
):
    """
    Get public promises for a user with stats (streak, progress, etc.).
    Authentication required.
    """
    try:
        promises_repo = PromisesRepository()
        actions_repo = ActionsRepository()
        reports_service = ReportsService(promises_repo, actions_repo)
        
        # Get all promises for the user
        all_promises = promises_repo.list_promises(user_id)
        
        # Filter to only public promises
        public_promises = [p for p in all_promises if p.visibility == "public"]
        
        # Get current time for calculations
        from datetime import datetime
        ref_time = datetime.now()
        
        # Calculate stats for each public promise
        badges = []
        for promise in public_promises:
            try:
                # Get promise summary with stats
                summary = reports_service.get_promise_summary(user_id, promise.id, ref_time)
                
                if not summary:
                    continue
                
                weekly_hours = summary.get('weekly_hours', 0.0)
                total_hours = summary.get('total_hours', 0.0)
                streak = summary.get('streak', 0)
                weekly_count = summary.get('weekly_count', 0)
                target_value = summary.get('target_value', 0)

                # Calculate progress percentage
                hours_promised = promise.hours_per_week
                if hours_promised > 0:
                    progress_percentage = min(100, (weekly_hours / hours_promised) * 100)
                elif target_value > 0:
                    # Count-based promise (e.g. check-in 3x/week)
                    progress_percentage = min(100, (weekly_count / target_value) * 100)
                else:
                    progress_percentage = 0.0
                
                is_count_based = hours_promised == 0 and target_value > 0
                badges.append(
                    PublicPromiseBadge(
                        promise_id=promise.id,
                        text=promise.text.replace('_', ' '),
                        hours_promised=hours_promised,
                        hours_spent=total_hours,
                        weekly_hours=weekly_hours,
                        streak=streak,
                        progress_percentage=progress_percentage,
                        metric_type="count" if is_count_based else "hours",
                        target_value=target_value if is_count_based else hours_promised,
                        achieved_value=weekly_count if is_count_based else weekly_hours,
                    )
                )
            except Exception as e:
                logger.warning(f"Error calculating stats for promise {promise.id}: {e}")
                continue
        
        return badges
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting public promises for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get public promises: {str(e)}")
