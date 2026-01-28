"""
Promise-related endpoints.
"""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from ..dependencies import get_current_user, get_settings_repo
from ..schemas import (
    UpdateVisibilityRequest, UpdateRecurringRequest, UpdatePromiseRequest,
    LogActionRequest, ScheduleSlotRequest, UpdateScheduleRequest,
    ReminderRequest, UpdateRemindersRequest, CheckinRequest, WeeklyNoteRequest
)
from repositories.promises_repo import PromisesRepository
from repositories.actions_repo import ActionsRepository
from repositories.templates_repo import TemplatesRepository
from repositories.instances_repo import InstancesRepository
from repositories.schedules_repo import SchedulesRepository
from repositories.reminders_repo import RemindersRepository
from services.reminder_dispatch import ReminderDispatchService
from db.postgres_db import get_db_session, utc_now_iso, resolve_promise_uuid, date_from_iso, dt_to_utc_iso
from sqlalchemy import text
from utils.logger import get_logger

router = APIRouter(prefix="/api", tags=["promises"])
logger = get_logger(__name__)


@router.patch("/promises/{promise_id}/visibility")
async def update_promise_visibility(
    request: Request,
    promise_id: str,
    vis_request: UpdateVisibilityRequest,
    user_id: int = Depends(get_current_user)
):
    """Update promise visibility. If making public, creates/links to marketplace template."""
    try:
        if vis_request.visibility not in ["private", "public"]:
            raise HTTPException(status_code=400, detail="Visibility must be 'private' or 'public'")
        
        promises_repo = PromisesRepository(request.app.state.root_dir)
        promise = promises_repo.get_promise(user_id, promise_id)
        
        if not promise:
            raise HTTPException(status_code=404, detail="Promise not found")
        
        was_public = promise.visibility == "public"
        promise.visibility = vis_request.visibility
        promises_repo.upsert_promise(user_id, promise)
        
        # If making public, create/upsert marketplace template
        if vis_request.visibility == "public" and not was_public:
            templates_repo = TemplatesRepository(request.app.state.root_dir)
            
            # Get promise_uuid first
            user_str = str(user_id)
            with get_db_session() as session:
                promise_uuid = resolve_promise_uuid(session, user_str, promise_id)
            
            if not promise_uuid:
                logger.warning(f"Could not resolve promise_uuid for promise {promise_id}, skipping template creation")
            else:
                # Build canonical key: normalized text + metric type + target
                normalized_text = promise.text.lower().strip().replace("_", " ").replace("  ", " ")
                # Determine metric type from promise (hours_per_week > 0 = hours, else count)
                metric_type = "hours" if promise.hours_per_week > 0 else "count"
                target_value = promise.hours_per_week if metric_type == "hours" else 0.0
                canonical_key = f"{normalized_text}|{metric_type}|{target_value}"
                
                # Check if template with this canonical_key exists
                with get_db_session() as session:
                    existing_template = session.execute(
                        text("""
                            SELECT template_id FROM promise_templates
                            WHERE canonical_key = :canonical_key
                            LIMIT 1
                        """),
                        {"canonical_key": canonical_key}
                    ).fetchone()
                
                template_id = None
                if existing_template:
                    template_id = existing_template[0]
                else:
                    # Create new template from promise
                    template_data = {
                        "title": promise.text.replace("_", " "),
                        "category": "general",
                        "level": "beginner",
                        "why": f"Track progress on {promise.text.replace('_', ' ')}",
                        "done": f"Complete {promise.text.replace('_', ' ')}",
                        "effort": "medium",
                        "template_kind": "commitment",
                        "metric_type": metric_type,
                        "target_value": target_value,
                        "target_direction": "at_least",
                        "estimated_hours_per_unit": 1.0,
                        "duration_type": "week" if promise.recurring else "one_time",
                        "duration_weeks": 1 if promise.recurring else None,
                        "is_active": True,
                        "canonical_key": canonical_key,
                        "created_by_user_id": str(user_id),
                        "source_promise_uuid": promise_uuid,
                        "origin": "user_public"
                    }
                    template_id = templates_repo.create_template(template_data)
                
                # Link promise to template via promise_instances (idempotent due to unique constraint)
                with get_db_session() as session:
                    if promise_uuid:
                        # Upsert instance link (ON CONFLICT DO NOTHING if unique constraint exists)
                        try:
                            session.execute(
                                text("""
                                    INSERT INTO promise_instances (
                                        instance_id, user_id, template_id, promise_uuid, status,
                                        metric_type, target_value, estimated_hours_per_unit,
                                        start_date, end_date, created_at_utc, updated_at_utc
                                    ) VALUES (
                                        gen_random_uuid()::text, :user_id, :template_id, :promise_uuid, 'active',
                                        :metric_type, :target_value, 1.0,
                                        COALESCE(:start_date, CURRENT_DATE::text), :end_date,
                                        :now, :now
                                    )
                                    ON CONFLICT (promise_uuid) DO UPDATE SET
                                        template_id = EXCLUDED.template_id,
                                        updated_at_utc = EXCLUDED.updated_at_utc
                                """),
                                {
                                    "user_id": user_str,
                                    "template_id": template_id,
                                    "promise_uuid": promise_uuid,
                                    "metric_type": metric_type,
                                    "target_value": target_value,
                                    "start_date": promise.start_date.isoformat() if promise.start_date else None,
                                    "end_date": promise.end_date.isoformat() if promise.end_date else None,
                                    "now": utc_now_iso()
                                }
                            )
                        except Exception as e:
                            # If unique constraint doesn't exist yet, try without ON CONFLICT
                            logger.warning(f"Could not upsert instance link (may need migration): {e}")
                            # Try simple insert (will fail if duplicate, that's OK)
                            try:
                                session.execute(
                                    text("""
                                        INSERT INTO promise_instances (
                                            instance_id, user_id, template_id, promise_uuid, status,
                                            metric_type, target_value, estimated_hours_per_unit,
                                            start_date, end_date, created_at_utc, updated_at_utc
                                        ) VALUES (
                                            gen_random_uuid()::text, :user_id, :template_id, :promise_uuid, 'active',
                                            :metric_type, :target_value, 1.0,
                                            COALESCE(:start_date, CURRENT_DATE::text), :end_date,
                                            :now, :now
                                        )
                                    """),
                                    {
                                        "user_id": user_str,
                                        "template_id": template_id,
                                        "promise_uuid": promise_uuid,
                                        "metric_type": metric_type,
                                        "target_value": target_value,
                                        "start_date": promise.start_date.isoformat() if promise.start_date else None,
                                        "end_date": promise.end_date.isoformat() if promise.end_date else None,
                                        "now": utc_now_iso()
                                    }
                                )
                            except Exception:
                                # Already linked, ignore
                                pass
        
        return {"status": "success", "visibility": promise.visibility}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating promise visibility: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update visibility: {str(e)}")


@router.patch("/promises/{promise_id}/recurring")
async def update_promise_recurring(
    request: Request,
    promise_id: str,
    rec_request: UpdateRecurringRequest,
    user_id: int = Depends(get_current_user)
):
    """Update promise recurring status."""
    try:
        promises_repo = PromisesRepository(request.app.state.root_dir)
        promise = promises_repo.get_promise(user_id, promise_id)
        
        if not promise:
            raise HTTPException(status_code=404, detail="Promise not found")
        
        promise.recurring = rec_request.recurring
        promises_repo.upsert_promise(user_id, promise)
        
        return {"status": "success", "recurring": promise.recurring}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating promise recurring status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update recurring status: {str(e)}")


@router.patch("/promises/{promise_id}")
async def update_promise(
    request: Request,
    promise_id: str,
    update_request: UpdatePromiseRequest,
    user_id: int = Depends(get_current_user)
):
    """Update promise fields (text, hours_per_week, end_date)."""
    try:
        from services.planner_api_adapter import PlannerAPIAdapter
        from datetime import date as date_type
        
        plan_keeper = PlannerAPIAdapter(request.app.state.root_dir)
        
        # Parse end_date if provided
        end_date_obj = None
        if update_request.end_date:
            try:
                end_date_obj = date_type.fromisoformat(update_request.end_date)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid end_date format: {update_request.end_date}. Expected YYYY-MM-DD")
        
        # Get current promise to validate end_date >= start_date
        promises_repo = PromisesRepository(request.app.state.root_dir)
        current_promise = promises_repo.get_promise(user_id, promise_id)
        
        if not current_promise:
            raise HTTPException(status_code=404, detail="Promise not found")
        
        # Validate end_date >= start_date if both are set
        if end_date_obj and current_promise.start_date:
            if end_date_obj < current_promise.start_date:
                raise HTTPException(
                    status_code=400, 
                    detail=f"end_date ({end_date_obj}) must be >= start_date ({current_promise.start_date})"
                )
        
        # Validate hours_per_week if provided
        if update_request.hours_per_week is not None:
            if update_request.hours_per_week <= 0:
                raise HTTPException(status_code=400, detail="hours_per_week must be a positive number")
        
        # Update promise using PlannerAPIAdapter
        result = plan_keeper.update_promise(
            user_id=user_id,
            promise_id=promise_id,
            promise_text=update_request.text,
            hours_per_week=update_request.hours_per_week,
            end_date=end_date_obj
        )
        
        # Check if update was successful (returns error message string on failure)
        if result and result.startswith("Promise with ID"):
            raise HTTPException(status_code=404, detail=result)
        elif result and ("must be" in result or "must be a" in result):
            raise HTTPException(status_code=400, detail=result)
        
        return {"status": "success", "message": result or "Promise updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating promise: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update promise: {str(e)}")


@router.post("/actions")
async def log_action(
    request: Request,
    action_request: LogActionRequest,
    user_id: int = Depends(get_current_user)
):
    """Log an action (time spent) for a promise."""
    try:
        if action_request.time_spent <= 0:
            raise HTTPException(status_code=400, detail="Time spent must be positive")
        
        # Parse datetime if provided, otherwise use current time
        if action_request.action_datetime:
            try:
                action_datetime = datetime.fromisoformat(action_request.action_datetime)
                # If timezone-aware, convert to naive datetime
                if action_datetime.tzinfo is not None:
                    import pytz
                    settings_repo = get_settings_repo(request)
                    settings = settings_repo.get_settings(user_id)
                    user_tz = settings.timezone if settings and settings.timezone not in (None, "DEFAULT") else "UTC"
                    tz = pytz.timezone(user_tz)
                    action_datetime = action_datetime.astimezone(tz).replace(tzinfo=None)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid action_datetime format")
        else:
            action_datetime = datetime.now()
        
        # Verify promise exists
        promises_repo = PromisesRepository(request.app.state.root_dir)
        promise = promises_repo.get_promise(user_id, action_request.promise_id)
        if not promise:
            raise HTTPException(status_code=404, detail="Promise not found")
        
        # Create and save action
        from models.models import Action
        action = Action(
            user_id=str(user_id),
            promise_id=action_request.promise_id,
            action="log_time",
            time_spent=action_request.time_spent,
            at=action_datetime,
            notes=action_request.notes if action_request.notes and action_request.notes.strip() else None
        )
        
        actions_repo = ActionsRepository(request.app.state.root_dir)
        actions_repo.append_action(action)
        
        return {"status": "success", "message": "Action logged successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error logging action: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to log action: {str(e)}")


@router.post("/promises/{promise_id}/snooze")
async def snooze_promise(
    request: Request,
    promise_id: str,
    user_id: int = Depends(get_current_user)
):
    """Snooze a promise until next week (hide from current week)."""
    try:
        promises_repo = PromisesRepository(request.app.state.root_dir)
        promise = promises_repo.get_promise(user_id, promise_id)
        
        if not promise:
            raise HTTPException(status_code=404, detail="Promise not found")
        
        # Calculate next week's start date (Monday)
        today = datetime.now().date()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7  # If today is Monday, go to next Monday
        next_monday = today + timedelta(days=days_until_monday)
        
        # Update promise start_date to next week
        promise.start_date = next_monday
        promises_repo.upsert_promise(user_id, promise)
        
        return {"status": "success", "message": f"Promise snoozed until {next_monday.isoformat()}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error snoozing promise: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to snooze promise: {str(e)}")


@router.get("/promises/{promise_id}/schedule")
async def get_promise_schedule(
    request: Request,
    promise_id: str,
    user_id: int = Depends(get_current_user)
):
    """Get schedule slots for a promise."""
    try:
        promises_repo = PromisesRepository(request.app.state.root_dir)
        schedules_repo = SchedulesRepository(request.app.state.root_dir)
        
        promise = promises_repo.get_promise(user_id, promise_id)
        if not promise:
            raise HTTPException(status_code=404, detail="Promise not found")
        
        # Get promise_uuid
        user_str = str(user_id)
        with get_db_session() as session:
            promise_uuid = resolve_promise_uuid(session, user_str, promise_id)
            if not promise_uuid:
                raise HTTPException(status_code=404, detail="Promise UUID not found")
        
        slots = schedules_repo.list_slots(promise_uuid, is_active=True)
        return {"slots": slots}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting promise schedule: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get schedule: {str(e)}")


@router.put("/promises/{promise_id}/schedule")
async def update_promise_schedule(
    request: Request,
    promise_id: str,
    schedule_request: UpdateScheduleRequest,
    user_id: int = Depends(get_current_user)
):
    """Replace schedule slots for a promise."""
    try:
        from datetime import time as time_type
        promises_repo = PromisesRepository(request.app.state.root_dir)
        schedules_repo = SchedulesRepository(request.app.state.root_dir)
        
        promise = promises_repo.get_promise(user_id, promise_id)
        if not promise:
            raise HTTPException(status_code=404, detail="Promise not found")
        
        # Get promise_uuid
        user_str = str(user_id)
        with get_db_session() as session:
            promise_uuid = resolve_promise_uuid(session, user_str, promise_id)
            if not promise_uuid:
                raise HTTPException(status_code=404, detail="Promise UUID not found")
        
        # Validate weekdays
        for slot_req in schedule_request.slots:
            if slot_req.weekday < 0 or slot_req.weekday > 6:
                raise HTTPException(status_code=400, detail="Weekday must be 0-6")
        
        # Convert to slot data format
        slots_data = []
        for slot_req in schedule_request.slots:
            start_time = time_type.fromisoformat(slot_req.start_local_time) if ":" in slot_req.start_local_time else time_type.fromisoformat(slot_req.start_local_time + ":00")
            end_time = None
            if slot_req.end_local_time:
                end_time = time_type.fromisoformat(slot_req.end_local_time) if ":" in slot_req.end_local_time else time_type.fromisoformat(slot_req.end_local_time + ":00")
            
            slot_data = {
                "promise_uuid": promise_uuid,
                "weekday": slot_req.weekday,
                "start_local_time": start_time,
                "end_local_time": end_time,
                "tz": slot_req.tz,
                "start_date": date_from_iso(slot_req.start_date) if slot_req.start_date else None,
                "end_date": date_from_iso(slot_req.end_date) if slot_req.end_date else None,
                "is_active": True
            }
            slots_data.append(slot_data)
        
        schedules_repo.replace_slots(promise_uuid, slots_data)
        
        return {"status": "success", "message": "Schedule updated", "slots_count": len(slots_data)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating promise schedule: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update schedule: {str(e)}")


@router.get("/promises/{promise_id}/reminders")
async def get_promise_reminders(
    request: Request,
    promise_id: str,
    user_id: int = Depends(get_current_user)
):
    """Get reminders for a promise."""
    try:
        promises_repo = PromisesRepository(request.app.state.root_dir)
        reminders_repo = RemindersRepository(request.app.state.root_dir)
        
        promise = promises_repo.get_promise(user_id, promise_id)
        if not promise:
            raise HTTPException(status_code=404, detail="Promise not found")
        
        # Get promise_uuid
        user_str = str(user_id)
        with get_db_session() as session:
            promise_uuid = resolve_promise_uuid(session, user_str, promise_id)
            if not promise_uuid:
                raise HTTPException(status_code=404, detail="Promise UUID not found")
        
        reminders = reminders_repo.list_reminders(promise_uuid, enabled=None)
        return {"reminders": reminders}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting promise reminders: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get reminders: {str(e)}")


@router.put("/promises/{promise_id}/reminders")
async def update_promise_reminders(
    request: Request,
    promise_id: str,
    reminders_request: UpdateRemindersRequest,
    user_id: int = Depends(get_current_user)
):
    """Replace reminders for a promise."""
    try:
        from datetime import time as time_type
        promises_repo = PromisesRepository(request.app.state.root_dir)
        reminders_repo = RemindersRepository(request.app.state.root_dir)
        dispatch_service = ReminderDispatchService(request.app.state.root_dir)
        
        promise = promises_repo.get_promise(user_id, promise_id)
        if not promise:
            raise HTTPException(status_code=404, detail="Promise not found")
        
        # Get promise_uuid
        user_str = str(user_id)
        with get_db_session() as session:
            promise_uuid = resolve_promise_uuid(session, user_str, promise_id)
            if not promise_uuid:
                raise HTTPException(status_code=404, detail="Promise UUID not found")
        
        # Validate reminders
        for rem_req in reminders_request.reminders:
            if rem_req.kind not in ["slot_offset", "fixed_time"]:
                raise HTTPException(status_code=400, detail="Reminder kind must be 'slot_offset' or 'fixed_time'")
            
            if rem_req.kind == "slot_offset":
                if not rem_req.slot_id:
                    raise HTTPException(status_code=400, detail="slot_id required for slot_offset reminders")
            elif rem_req.kind == "fixed_time":
                if rem_req.weekday is None or not rem_req.time_local:
                    raise HTTPException(status_code=400, detail="weekday and time_local required for fixed_time reminders")
                if rem_req.weekday < 0 or rem_req.weekday > 6:
                    raise HTTPException(status_code=400, detail="weekday must be 0-6")
        
        # Convert to reminder data format
        reminders_data = []
        for rem_req in reminders_request.reminders:
            reminder_data = {
                "promise_uuid": promise_uuid,
                "kind": rem_req.kind,
                "slot_id": rem_req.slot_id,
                "offset_minutes": rem_req.offset_minutes,
                "weekday": rem_req.weekday,
                "time_local": time_type.fromisoformat(rem_req.time_local) if rem_req.time_local and ":" in rem_req.time_local else (time_type.fromisoformat(rem_req.time_local + ":00") if rem_req.time_local else None),
                "tz": rem_req.tz,
                "enabled": rem_req.enabled if rem_req.enabled is not None else True
            }
            
            # Compute next_run_at_utc
            next_run = dispatch_service.compute_next_run_at_utc(reminder_data, user_id)
            if next_run:
                reminder_data["next_run_at_utc"] = dt_to_utc_iso(next_run)
            
            reminders_data.append(reminder_data)
        
        reminders_repo.replace_reminders(promise_uuid, reminders_data)
        
        return {"status": "success", "message": "Reminders updated", "reminders_count": len(reminders_data)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating promise reminders: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update reminders: {str(e)}")


@router.post("/promises/{promise_id}/checkin")
async def checkin_promise(
    request: Request,
    promise_id: str,
    checkin_request: Optional[CheckinRequest] = None,
    user_id: int = Depends(get_current_user)
):
    """Record a check-in for a promise (count-based templates)."""
    try:
        from dateutil.parser import parse as parse_datetime
        
        promises_repo = PromisesRepository(request.app.state.root_dir)
        promise = promises_repo.get_promise(user_id, promise_id)
        
        if not promise:
            raise HTTPException(status_code=404, detail="Promise not found")
        
        # Parse datetime if provided
        action_datetime = None
        if checkin_request and checkin_request.action_datetime:
            try:
                action_datetime = parse_datetime(checkin_request.action_datetime)
                if action_datetime.tzinfo is not None:
                    import pytz
                    settings_repo = get_settings_repo(request)
                    settings = settings_repo.get_settings(user_id)
                    user_tz = settings.timezone if settings and settings.timezone not in (None, "DEFAULT") else "UTC"
                    tz = pytz.timezone(user_tz)
                    action_datetime = action_datetime.astimezone(tz).replace(tzinfo=None)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid action_datetime format")
        else:
            action_datetime = datetime.now()
        
        # Create check-in action
        from models.models import Action
        from models.enums import ActionType
        action = Action(
            user_id=str(user_id),
            promise_id=promise_id,
            action=ActionType.CHECKIN.value,
            time_spent=0.0,
            at=action_datetime
        )
        
        actions_repo = ActionsRepository(request.app.state.root_dir)
        actions_repo.append_action(action)
        
        return {"status": "success", "message": "Check-in recorded successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error recording check-in: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to record check-in: {str(e)}")


@router.post("/promises/{promise_id}/weekly-note")
async def update_weekly_note(
    request: Request,
    promise_id: str,
    note_request: WeeklyNoteRequest,
    user_id: int = Depends(get_current_user)
):
    """Update weekly note for a promise instance."""
    try:
        instances_repo = InstancesRepository(request.app.state.root_dir)
        from repositories.reviews_repo import ReviewsRepository
        reviews_repo = ReviewsRepository(request.app.state.root_dir)
        
        # Find instance by promise_id (PostgreSQL)
        user = str(user_id)
        with get_db_session() as session:
            promise_uuid = resolve_promise_uuid(session, user, promise_id)
            if not promise_uuid:
                raise HTTPException(status_code=404, detail="Promise not found")
        
        instance = instances_repo.get_instance_by_promise_uuid(user_id, promise_uuid)
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found for this promise")
        
        success = reviews_repo.update_weekly_note(
            user_id, instance["instance_id"], note_request.week_start, note_request.note
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Weekly review not found")
        
        return {"status": "success", "message": "Weekly note updated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating weekly note: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update weekly note: {str(e)}")


@router.get("/promises/{promise_id}/logs")
async def get_promise_logs(
    request: Request,
    promise_id: str,
    limit: int = 20,
    user_id: int = Depends(get_current_user)
):
    """Get recent logs/actions for a promise."""
    try:
        promises_repo = PromisesRepository(request.app.state.root_dir)
        actions_repo = ActionsRepository(request.app.state.root_dir)
        
        # Verify promise exists and belongs to user
        promise = promises_repo.get_promise(user_id, promise_id)
        if not promise:
            raise HTTPException(status_code=404, detail="Promise not found")
        
        # Get all actions for this promise, sorted by date (most recent first)
        all_actions = actions_repo.list_actions(user_id)
        promise_actions = [
            a for a in all_actions 
            if (a.promise_id or "").strip().upper() == promise_id.strip().upper()
        ]
        
        # Sort by date descending and limit
        promise_actions.sort(key=lambda a: a.at, reverse=True)
        recent_actions = promise_actions[:limit]
        
        # Format response
        logs = []
        for action in recent_actions:
            # Format time spent
            if action.time_spent > 0:
                hours = int(action.time_spent)
                minutes = int((action.time_spent - hours) * 60)
                if hours > 0 and minutes > 0:
                    time_str = f"{hours} hour{'s' if hours != 1 else ''} {minutes} minute{'s' if minutes != 1 else ''}"
                elif hours > 0:
                    time_str = f"{hours} hour{'s' if hours != 1 else ''}"
                else:
                    time_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
            else:
                time_str = "check-in"
            
            # Format date
            date = action.at.date()
            weekday = action.at.strftime("%A")
            day = date.day
            month = action.at.strftime("%b")
            year = action.at.year
            # Format: "Wednesday 21 Dec." (without year if current year)
            from datetime import datetime
            current_year = datetime.now().year
            if year == current_year:
                date_str = f"{weekday} {day} {month}."
            else:
                date_str = f"{weekday} {day} {month}. {year}"
            
            logs.append({
                "datetime": action.at.isoformat(),
                "date": date_str,
                "time_spent": action.time_spent,
                "time_str": time_str,
                "notes": action.notes if action.notes else None
            })
        
        return {"logs": logs}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting promise logs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get promise logs: {str(e)}")