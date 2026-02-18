"""
User-related endpoints.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from ..dependencies import get_current_user, get_settings_repo, update_user_activity, get_reports_service
from ..schemas import (
    WeeklyReportResponse, UserInfoResponse, TimezoneUpdateRequest,
    UserSettingsUpdateRequest, PublicUser, PublicUsersResponse
)
from repositories.follows_repo import FollowsRepository
from repositories.settings_repo import SettingsRepository
from utils.time_utils import get_week_range
from utils.logger import get_logger
from db.postgres_db import get_db_session
from sqlalchemy import text

router = APIRouter(prefix="/api", tags=["users"])
logger = get_logger(__name__)

# Module-level cache for pending follow notifications
_pending_follow_notification_jobs: dict = {}


@router.get("/weekly", response_model=WeeklyReportResponse)
async def get_weekly_report(
    request: Request,
    user_id: int = Depends(get_current_user),
    ref_time: Optional[str] = None
):
    """
    Get weekly report for the authenticated user.
    
    Args:
        ref_time: Optional ISO format datetime string for reference time.
                 Defaults to current time in user's timezone.
    """
    try:
        # Get user timezone (fall back to UTC if not set or is DEFAULT placeholder)
        settings_repo = get_settings_repo(request)
        settings = settings_repo.get_settings(user_id)
        user_tz = settings.timezone if settings and settings.timezone not in (None, "DEFAULT") else "UTC"
        
        # Parse reference time or use current time
        if ref_time:
            try:
                reference_time = datetime.fromisoformat(ref_time)
                # If timezone-aware, convert to naive datetime in user's timezone
                if reference_time.tzinfo is not None:
                    import pytz
                    user_tz_obj = pytz.timezone(user_tz)
                    # Convert to user timezone, then make naive
                    reference_time = reference_time.astimezone(user_tz_obj).replace(tzinfo=None)
                logger.debug(f"[DEBUG] Parsed ref_time: {ref_time} -> {reference_time} (user_tz: {user_tz})")
            except ValueError as e:
                logger.error(f"[ERROR] Invalid ref_time format: {ref_time}, error: {e}")
                raise HTTPException(status_code=400, detail=f"Invalid ref_time format: {ref_time}")
        else:
            import pytz
            tz = pytz.timezone(user_tz)
            reference_time = datetime.now(tz).replace(tzinfo=None)  # Make naive
            logger.debug(f"[DEBUG] Using current time as ref_time: {reference_time} (user_tz: {user_tz})")
        
        # Get weekly summary
        reports_service = get_reports_service(request, user_id)
        logger.debug(f"[DEBUG] Getting weekly summary for user {user_id}, ref_time: {reference_time}")
        summary = reports_service.get_weekly_summary_with_sessions(user_id, reference_time)
        logger.debug(f"[DEBUG] Weekly summary result: {len(summary)} promises, keys: {list(summary.keys())}")
        
        # Calculate week range
        week_start, week_end = get_week_range(reference_time)
        # For display, week_end should be Sunday (6 days after Monday), not next Monday
        week_end_display = week_start + timedelta(days=6)  # Sunday
        
        # Calculate totals
        total_promised = 0.0
        total_spent = 0.0
        for data in summary.values():
            total_promised += float(data.get("hours_promised", 0) or 0)
            total_spent += float(data.get("hours_spent", 0) or 0)
        
        # Convert dates in sessions to ISO format strings
        formatted_summary = {}
        for pid, data in summary.items():
            formatted_data = dict(data)
            if "sessions" in formatted_data:
                formatted_data["sessions"] = [
                    {
                        "date": s["date"].isoformat() if hasattr(s["date"], "isoformat") else str(s["date"]),
                        "hours": s["hours"]
                    }
                    for s in formatted_data["sessions"]
                ]
            formatted_summary[pid] = formatted_data
        
        return WeeklyReportResponse(
            week_start=week_start.date().isoformat(),  # Send as date-only string (YYYY-MM-DD)
            week_end=week_end_display.date().isoformat(),  # Send as date-only string (YYYY-MM-DD)
            total_promised=round(total_promised, 2),
            total_spent=round(total_spent, 2),
            promises=formatted_summary
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting weekly report for user {user_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user", response_model=UserInfoResponse)
async def get_user_info(request: Request, user_id: int = Depends(get_current_user)):
    """Get user settings/info for the authenticated user."""
    try:
        settings_repo = get_settings_repo(request)
        settings = settings_repo.get_settings(user_id)
        
        return UserInfoResponse(
            user_id=user_id,
            timezone=settings.timezone if settings else "UTC",
            language=settings.language if settings else "en",
            first_name=settings.first_name if settings else None,
            voice_mode=settings.voice_mode if settings else None
        )
    except Exception as e:
        logger.exception(f"Error getting user info for user {user_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/user/settings", response_model=UserInfoResponse)
async def update_user_settings(
    request: Request,
    payload: UserSettingsUpdateRequest,
    user_id: int = Depends(get_current_user)
):
    """
    Update user settings (partial update). Only provided fields are updated.
    Valid: timezone (IANA), language (en|fa|fr), voice_mode (enabled|disabled|null), first_name.
    """
    from zoneinfo import ZoneInfo
    from models.models import UserSettings

    settings_repo = get_settings_repo(request)
    settings = settings_repo.get_settings(user_id)
    if not settings:
        settings = UserSettings(user_id=str(user_id))

    if payload.timezone is not None:
        try:
            ZoneInfo(payload.timezone)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid timezone: {payload.timezone}. Error: {str(e)}")
        settings.timezone = payload.timezone

    if payload.language is not None:
        if payload.language not in ("en", "fa", "fr"):
            raise HTTPException(status_code=400, detail="language must be one of: en, fa, fr")
        settings.language = payload.language

    if payload.voice_mode is not None:
        if payload.voice_mode not in ("enabled", "disabled"):
            raise HTTPException(status_code=400, detail="voice_mode must be one of: enabled, disabled")
        settings.voice_mode = payload.voice_mode

    if payload.first_name is not None:
        settings.first_name = payload.first_name

    settings_repo.save_settings(settings)
    update_user_activity(request, user_id)

    return UserInfoResponse(
        user_id=user_id,
        timezone=settings.timezone or "UTC",
        language=settings.language or "en",
        first_name=settings.first_name,
        voice_mode=settings.voice_mode
    )


@router.post("/user/timezone")
async def update_user_timezone(
    request: Request,
    tz_request: TimezoneUpdateRequest,
    user_id: int = Depends(get_current_user)
):
    """
    Update user timezone.
    Automatically called by Mini App on load to detect and set timezone.
    Only updates if user hasn't set a timezone yet, or if explicitly updating.
    """
    try:
        # Update user's last_seen_utc - user is active (opening Mini App)
        update_user_activity(request, user_id)
        
        from zoneinfo import ZoneInfo
        
        # Validate timezone
        try:
            ZoneInfo(tz_request.tz)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid timezone: {tz_request.tz}. Error: {str(e)}"
            )
        
        settings_repo = get_settings_repo(request)
        settings = settings_repo.get_settings(user_id)
        
        # Only update if timezone is not set (defaults to "DEFAULT")
        # or if explicitly updating with force=True
        current_tz = settings.timezone if settings else None
        default_tzs = ["DEFAULT"]
        
        if tz_request.force:
            # Force update - update immediately
            if not settings:
                from models.models import UserSettings
                settings = UserSettings(user_id=str(user_id))
            
            settings.timezone = tz_request.tz
            settings_repo.save_settings(settings)
            
            logger.info(f"Updated timezone for user {user_id} to {tz_request.tz} (forced)")
            
            return {
                "status": "success",
                "message": f"Timezone updated to {tz_request.tz}",
                "timezone": tz_request.tz
            }
        elif not current_tz or current_tz in default_tzs:
            # Timezone is DEFAULT - queue delayed message instead of updating immediately
            # Cancel any existing pending timezone messages for this user
            delayed_service = request.app.state.delayed_message_service
            delayed_service.cancel_pending(user_id)
            
            # Queue message to be sent after 2 minutes of inactivity
            async def send_timezone_message():
                """Send timezone confirmation message to user."""
                try:
                    # Get user settings for language
                    user_settings = settings_repo.get_settings(user_id)
                    user_lang = user_settings.language if user_settings else "en"
                    
                    # Get message translations
                    from handlers.messages_store import get_message, Language
                    lang_map = {"en": Language.EN, "fa": Language.FA, "fr": Language.FR}
                    lang = lang_map.get(user_lang, Language.EN)
                    
                    prompt_msg = get_message("timezone_detected_prompt", lang, timezone=tz_request.tz)
                    use_btn = get_message("timezone_confirm_use_detected", lang, timezone=tz_request.tz)
                    not_now_btn = get_message("timezone_confirm_not_now", lang)
                    choose_btn = get_message("timezone_confirm_choose_different", lang)
                    
                    # Create inline keyboard
                    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
                    from cbdata import encode_cb
                    
                    # Get mini app URL
                    miniapp_url = os.getenv("MINIAPP_URL", "https://xaana.club")
                    timezone_url = f"{miniapp_url}/timezone"
                    
                    keyboard = InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton(use_btn, callback_data=encode_cb("tz_confirm", tz=tz_request.tz)),
                            InlineKeyboardButton(not_now_btn, callback_data=encode_cb("tz_not_now"))
                        ],
                        [
                            InlineKeyboardButton(choose_btn, web_app=WebAppInfo(url=timezone_url))
                        ]
                    ])
                    
                    # Send message
                    from telegram import Bot
                    bot = Bot(token=request.app.state.bot_token)
                    await bot.send_message(
                        chat_id=user_id,
                        text=prompt_msg,
                        reply_markup=keyboard,
                        parse_mode=None
                    )
                    
                    logger.info(f"Sent timezone confirmation message to user {user_id}")
                except Exception as e:
                    logger.error(f"Unexpected error sending timezone message to user {user_id}: {e}", exc_info=True)
            
            # Queue the message
            message_id = f"timezone_{user_id}_{int(datetime.now().timestamp())}"
            delayed_service.queue_message(
                user_id=user_id,
                message_func=send_timezone_message,
                delay_minutes=2,
                message_id=message_id
            )
            
            logger.info(f"Queued timezone confirmation message for user {user_id}, will send in 2 minutes if inactive")
            
            return {
                "status": "queued",
                "message": "Timezone confirmation message queued",
                "timezone": tz_request.tz
            }
        else:
            # Timezone already set, return current timezone
            return {
                "status": "unchanged",
                "message": f"Timezone already set to {current_tz}",
                "timezone": current_tz
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating timezone for user {user_id}")
        raise HTTPException(status_code=500, detail=f"Failed to update timezone: {str(e)}")


@router.get("/public/users", response_model=PublicUsersResponse)
async def get_public_users(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    user_id: int = Depends(get_current_user),
):
    """
    Get public list of most active users (authenticated only).
    
    Args:
        limit: Maximum number of users to return (1-100, default: 20)
    
    Returns:
        List of public user information ranked by activity
    """
    try:
        # IMPORTANT: Use the Postgres-backed DB (SQLAlchemy session) so counts and avatars
        # match followers/following + user detail pages.
        since_utc = (
            (datetime.now(timezone.utc) - timedelta(days=30))
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT 
                        u.user_id,
                        u.first_name,
                        u.last_name,
                        u.display_name,
                        u.username,
                        u.avatar_path,
                        u.avatar_file_unique_id,
                        u.last_seen_utc,
                        COALESCE(activity.activity_count, 0) as activity_count,
                        COALESCE(promise_counts.promise_count, 0) as promise_count
                    FROM users u
                    LEFT JOIN (
                        SELECT user_id, COUNT(*) as activity_count
                        FROM actions 
                        WHERE at_utc >= :since_utc
                        GROUP BY user_id
                    ) activity ON u.user_id = activity.user_id
                    LEFT JOIN (
                        SELECT user_id, COUNT(*) as promise_count
                        FROM promises
                        WHERE is_deleted = 0
                        GROUP BY user_id
                    ) promise_counts ON u.user_id = promise_counts.user_id
                    WHERE (u.avatar_visibility = 'public' OR u.avatar_visibility IS NULL)
                    ORDER BY activity_count DESC, u.last_seen_utc DESC NULLS LAST
                    LIMIT :limit;
                """),
                {"since_utc": since_utc, "limit": int(limit)},
            ).mappings().fetchall()

        from ..schemas import PublicUser
        users = []
        for r in rows:
            users.append(
                PublicUser(
                    user_id=str(r.get("user_id")),
                    first_name=r.get("first_name"),
                    last_name=r.get("last_name"),
                    display_name=r.get("display_name"),
                    username=r.get("username"),
                    avatar_path=r.get("avatar_path"),
                    avatar_file_unique_id=r.get("avatar_file_unique_id"),
                    activity_count=int(r.get("activity_count") or 0),
                    promise_count=int(r.get("promise_count") or 0),
                    last_seen_utc=r.get("last_seen_utc"),
                )
            )

        return PublicUsersResponse(users=users, total=len(users))
            
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting public users: {e}")
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Full traceback: {error_trace}")
        # Return a simpler error message for production
        raise HTTPException(status_code=500, detail=f"Failed to fetch users: {str(e)}")


@router.post("/users/{target_user_id}/follow")
async def follow_user(
    request: Request,
    target_user_id: int,
    user_id: int = Depends(get_current_user)
):
    """Follow a user."""
    try:
        if user_id == target_user_id:
            raise HTTPException(status_code=400, detail="Cannot follow yourself")
        
        follows_repo = FollowsRepository()
        success = follows_repo.follow(user_id, target_user_id)

        # Schedule follow notification after 2 minutes (cancellable if unfollow happens).
        # IMPORTANT: This should NOT depend on the followee's inactivity.
        if success:
            notification_key = (user_id, target_user_id)
            job_name = f"follow-notif-{user_id}-{target_user_id}"

            # Cancel any existing pending job for this relationship
            existing_job = _pending_follow_notification_jobs.get(notification_key)
            try:
                if existing_job and getattr(request.app.state, "delayed_message_service", None):
                    request.app.state.delayed_message_service.scheduler.cancel_job(existing_job)
            except Exception as e:
                logger.warning(f"Failed to cancel existing follow notification job {existing_job}: {e}")

            async def send_follow_notification_if_still_following(context=None):
                from ..notifications import send_follow_notification
                current_follows_repo = FollowsRepository()
                if not current_follows_repo.is_following(user_id, target_user_id):
                    logger.info(
                        f"Follow notification cancelled: user {user_id} unfollowed {target_user_id} before notification"
                    )
                    _pending_follow_notification_jobs.pop(notification_key, None)
                    return
                await send_follow_notification(
                    request.app.state.bot_token,
                    user_id,
                    target_user_id,
                )
                _pending_follow_notification_jobs.pop(notification_key, None)

            when_dt = datetime.now(timezone.utc) + timedelta(minutes=2)

            try:
                if getattr(request.app.state, "delayed_message_service", None):
                    request.app.state.delayed_message_service.scheduler.schedule_once(
                        name=job_name,
                        callback=send_follow_notification_if_still_following,
                        when_dt=when_dt,
                        data={"user_id": target_user_id, "follower_id": user_id, "followee_id": target_user_id},
                    )
                    _pending_follow_notification_jobs[notification_key] = job_name
                    logger.info(
                        f"Scheduled follow notification job {job_name} for user {target_user_id} (2-minute delay)"
                    )
                else:
                    raise RuntimeError("No delayed_message_service available")
            except Exception as e:
                # Fallback: send immediately
                logger.warning(f"Failed to schedule delayed follow notification, sending immediate: {e}")
                import asyncio
                from ..notifications import send_follow_notification

                asyncio.create_task(
                    send_follow_notification(
                        request.app.state.bot_token,
                        user_id,
                        target_user_id,
                    )
                )

            return {"status": "success", "message": "User followed successfully"}
        else:
            return {"status": "success", "message": "Already following this user"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Error following user {target_user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to follow user: {str(e)}")


@router.delete("/users/{target_user_id}/follow")
async def unfollow_user(
    request: Request,
    target_user_id: int,
    user_id: int = Depends(get_current_user)
):
    """Unfollow a user."""
    try:
        follows_repo = FollowsRepository()
        success = follows_repo.unfollow(user_id, target_user_id)
        
        if success:
            # Cancel pending follow notification if exists
            notification_key = (user_id, target_user_id)
            job_name = _pending_follow_notification_jobs.pop(notification_key, None)
            if job_name and getattr(request.app.state, "delayed_message_service", None):
                try:
                    request.app.state.delayed_message_service.scheduler.cancel_job(job_name)
                    logger.info(
                        f"Cancelled pending follow notification job {job_name} for user {target_user_id} from follower {user_id}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to cancel follow notification job {job_name}: {e}")

            return {"status": "success", "message": "User unfollowed successfully"}
        else:
            return {"status": "success", "message": "Not following this user"}
    except Exception as e:
        logger.exception(f"Error unfollowing user {target_user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to unfollow user: {str(e)}")


@router.get("/users/{user_id}", response_model=PublicUser)
async def get_user(
    request: Request,
    user_id: int,
    current_user_id: int = Depends(get_current_user)
):
    """Get public user information by ID."""
    try:
        settings_repo = SettingsRepository()
        follows_repo = FollowsRepository()
        
        # Get user settings
        settings = settings_repo.get_settings(user_id)
        if not settings:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Get activity count
        with get_db_session() as session:
            since_utc = (
                (datetime.now(timezone.utc) - timedelta(days=30))
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )
            activity_row = session.execute(
                text("""
                    SELECT COUNT(*) as activity_count
                    FROM actions 
                    WHERE user_id = :user_id AND at_utc >= :since_utc
                """),
                {"user_id": str(user_id), "since_utc": since_utc}
            ).mappings().fetchone()
            activity_count = int(activity_row["activity_count"] or 0) if activity_row else 0
            
            promise_row = session.execute(
                text("""
                    SELECT COUNT(*) as promise_count
                    FROM promises
                    WHERE user_id = :user_id AND is_deleted = 0
                """),
                {"user_id": str(user_id)}
            ).mappings().fetchone()
            promise_count = int(promise_row["promise_count"] or 0) if promise_row else 0
            
            # Get avatar path if available
            avatar_row = session.execute(
                text("""
                    SELECT avatar_path, avatar_file_unique_id
                    FROM users
                    WHERE user_id = :user_id
                """),
                {"user_id": str(user_id)}
            ).mappings().fetchone()
            avatar_path = avatar_row.get("avatar_path") if avatar_row else None
            avatar_file_unique_id = avatar_row.get("avatar_file_unique_id") if avatar_row else None
            
            # Get public promises using the existing service
            from repositories.promises_repo import PromisesRepository
            from repositories.actions_repo import ActionsRepository
            from services.reports import ReportsService
            
            promises_repo = PromisesRepository()
            actions_repo = ActionsRepository()
            reports_service = ReportsService(promises_repo, actions_repo)
            
            # Get all promises for the user
            all_promises = promises_repo.list_promises(user_id)
            
            # Filter to only public promises
            public_promise_list = [p for p in all_promises if p.visibility == "public"]
            
            # Get current time for calculations
            ref_time = datetime.now()
            
            # Calculate stats for each public promise
            public_promises = []
            for promise in public_promise_list:
                try:
                    # Get promise summary with stats
                    summary = reports_service.get_promise_summary(user_id, promise.id, ref_time)
                    
                    if not summary:
                        continue
                    
                    weekly_hours = summary.get('weekly_hours', 0.0)
                    total_hours = summary.get('total_hours', 0.0)
                    streak = summary.get('streak', 0)
                    
                    # Calculate progress percentage
                    hours_promised = promise.hours_per_week
                    if hours_promised > 0:
                        progress_percentage = min(100, (weekly_hours / hours_promised) * 100)
                    else:
                        progress_percentage = 0.0
                    
                    # Get metric_type and target_value from template if available
                    metric_type = "hours"
                    target_value = hours_promised
                    with get_db_session() as template_session:
                        template_row = template_session.execute(
                            text("""
                                SELECT pt.metric_type, pt.target_value
                                FROM promise_instances pi
                                JOIN promise_templates pt ON pi.template_id = pt.template_id
                                WHERE pi.promise_uuid = :promise_uuid
                                LIMIT 1
                            """),
                            {"promise_uuid": promise.promise_uuid}
                        ).mappings().fetchone()
                        if template_row:
                            metric_type = template_row.get("metric_type") or "hours"
                            target_value = float(template_row.get("target_value") or hours_promised)
                    
                    public_promises.append({
                        "promise_id": promise.id,
                        "text": promise.text.replace('_', ' '),
                        "hours_promised": hours_promised,
                        "hours_spent": total_hours,
                        "weekly_hours": weekly_hours,
                        "streak": streak,
                        "progress_percentage": progress_percentage,
                        "metric_type": metric_type,
                        "target_value": target_value,
                        "achieved_value": weekly_hours if metric_type == "hours" else summary.get('achieved_value', 0.0)
                    })
                except Exception as e:
                    logger.warning(f"Error calculating stats for promise {promise.id}: {e}")
                    continue
        
        return PublicUser(
            user_id=str(user_id),
            first_name=settings.first_name,
            username=settings.username,
            display_name=None,
            avatar_path=avatar_path,
            avatar_file_unique_id=avatar_file_unique_id,
            activity_count=activity_count,
            promise_count=promise_count,
            last_seen_utc=settings.last_seen.isoformat() if settings.last_seen else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get user: {str(e)}")


@router.get("/users/{target_user_id}/follow-status")
async def get_follow_status(
    request: Request,
    target_user_id: int,
    user_id: int = Depends(get_current_user)
):
    """Check if current user is following target user."""
    try:
        follows_repo = FollowsRepository()
        is_following = follows_repo.is_following(user_id, target_user_id)
        
        return {"is_following": is_following}
    except Exception as e:
        logger.exception(f"Error getting follow status for user {target_user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get follow status: {str(e)}")


@router.get("/users/{user_id}/followers", response_model=PublicUsersResponse)
async def get_followers(
    request: Request,
    user_id: int,
    current_user_id: int = Depends(get_current_user)
):
    """Get list of users that follow the specified user."""
    try:
        # Only allow viewing your own followers or if viewing another user's (for future expansion)
        if user_id != current_user_id:
            # For now, only allow viewing own followers
            raise HTTPException(status_code=403, detail="Can only view your own followers")
        
        follows_repo = FollowsRepository()
        settings_repo = SettingsRepository()
        
        # Get follower user IDs
        follower_ids = follows_repo.get_followers(user_id)
        
        # Enrich with user info
        users = []
        for follower_id_str in follower_ids:
            try:
                follower_id = int(follower_id_str)
                settings = settings_repo.get_settings(follower_id)
                
                # Get activity count (simplified - could be optimized)
                with get_db_session() as session:
                    since_utc = (
                        (datetime.now(timezone.utc) - timedelta(days=30))
                        .replace(microsecond=0)
                        .isoformat()
                        .replace("+00:00", "Z")
                    )
                    activity_row = session.execute(
                        text("""
                            SELECT COUNT(*) as activity_count
                            FROM actions 
                            WHERE user_id = :user_id AND at_utc >= :since_utc
                        """),
                        {"user_id": follower_id_str, "since_utc": since_utc}
                    ).mappings().fetchone()
                    activity_count = int(activity_row["activity_count"] or 0) if activity_row else 0
                    
                    promise_row = session.execute(
                        text("""
                            SELECT COUNT(*) as promise_count
                            FROM promises
                            WHERE user_id = :user_id AND is_deleted = 0
                        """),
                        {"user_id": follower_id_str}
                    ).mappings().fetchone()
                    promise_count = int(promise_row["promise_count"] or 0) if promise_row else 0
                
                # Get avatar path if available
                avatar_path = None
                avatar_file_unique_id = None
                with get_db_session() as session:
                    avatar_row = session.execute(
                        text("""
                            SELECT avatar_path, avatar_file_unique_id
                            FROM users
                            WHERE user_id = :user_id
                        """),
                        {"user_id": follower_id_str}
                    ).mappings().fetchone()
                    if avatar_row:
                        avatar_path = avatar_row.get("avatar_path")
                        avatar_file_unique_id = avatar_row.get("avatar_file_unique_id")
                
                users.append(
                    PublicUser(
                        user_id=follower_id_str,
                        first_name=settings.first_name,
                        username=settings.username,
                        display_name=None,
                        last_name=None,
                        avatar_path=avatar_path,
                        avatar_file_unique_id=avatar_file_unique_id,
                        activity_count=activity_count,
                        promise_count=promise_count,
                        last_seen_utc=None,
                    )
                )
            except Exception as e:
                logger.warning(f"Error enriching follower {follower_id_str}: {e}")
                continue
        
        return PublicUsersResponse(users=users, total=len(users))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting followers for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get followers: {str(e)}")


@router.get("/users/{user_id}/following", response_model=PublicUsersResponse)
async def get_following(
    request: Request,
    user_id: int,
    current_user_id: int = Depends(get_current_user)
):
    """Get list of users that the specified user follows."""
    try:
        # Only allow viewing your own following list
        if user_id != current_user_id:
            raise HTTPException(status_code=403, detail="Can only view your own following list")
        
        follows_repo = FollowsRepository()
        settings_repo = SettingsRepository()
        
        # Get following user IDs
        following_ids = follows_repo.get_following(user_id)
        
        # Enrich with user info
        users = []
        for following_id_str in following_ids:
            try:
                following_id = int(following_id_str)
                settings = settings_repo.get_settings(following_id)
                
                # Get activity count
                with get_db_session() as session:
                    since_utc = (
                        (datetime.now(timezone.utc) - timedelta(days=30))
                        .replace(microsecond=0)
                        .isoformat()
                        .replace("+00:00", "Z")
                    )
                    activity_row = session.execute(
                        text("""
                            SELECT COUNT(*) as activity_count
                            FROM actions 
                            WHERE user_id = :user_id AND at_utc >= :since_utc
                        """),
                        {"user_id": following_id_str, "since_utc": since_utc}
                    ).mappings().fetchone()
                    activity_count = int(activity_row["activity_count"] or 0) if activity_row else 0
                    
                    promise_row = session.execute(
                        text("""
                            SELECT COUNT(*) as promise_count
                            FROM promises
                            WHERE user_id = :user_id AND is_deleted = 0
                        """),
                        {"user_id": following_id_str}
                    ).mappings().fetchone()
                    promise_count = int(promise_row["promise_count"] or 0) if promise_row else 0
                
                # Get avatar path if available
                avatar_path = None
                avatar_file_unique_id = None
                with get_db_session() as session:
                    avatar_row = session.execute(
                        text("""
                            SELECT avatar_path, avatar_file_unique_id
                            FROM users
                            WHERE user_id = :user_id
                        """),
                        {"user_id": following_id_str}
                    ).mappings().fetchone()
                    if avatar_row:
                        avatar_path = avatar_row.get("avatar_path")
                        avatar_file_unique_id = avatar_row.get("avatar_file_unique_id")
                
                users.append(
                    PublicUser(
                        user_id=following_id_str,
                        first_name=settings.first_name,
                        username=settings.username,
                        display_name=None,
                        last_name=None,
                        avatar_path=avatar_path,
                        avatar_file_unique_id=avatar_file_unique_id,
                        activity_count=activity_count,
                        promise_count=promise_count,
                        last_seen_utc=None,
                    )
                )
            except Exception as e:
                logger.warning(f"Error enriching following {following_id_str}: {e}")
                continue
        
        return PublicUsersResponse(users=users, total=len(users))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting following for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get following: {str(e)}")
