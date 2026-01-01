from typing import Dict, Any, List
from datetime import datetime, timedelta, date
import os
import tempfile
import uuid
import logging

from repositories.promises_repo import PromisesRepository
from repositories.actions_repo import ActionsRepository
from utils.time_utils import get_week_range
from utils.promise_id import normalize_promise_id, promise_ids_equal


logger = logging.getLogger(__name__)


class ReportsService:
    def __init__(self, promises_repo: PromisesRepository, actions_repo: ActionsRepository):
        self.promises_repo = promises_repo
        self.actions_repo = actions_repo

    def get_weekly_summary(self, user_id: int, ref_time: datetime) -> Dict[str, Any]:
        """Get weekly summary data for a user."""
        # Get week boundaries
        week_start, week_end = get_week_range(ref_time)
        
        # Get all promises
        promises = self.promises_repo.list_promises(user_id)
        
        # Get actions from this week
        actions = self.actions_repo.list_actions(user_id, since=week_start)
        
        # Initialize report data (keyed by canonical promise.id from storage)
        report_data: Dict[str, Any] = {}
        canonical_by_norm: Dict[str, str] = {}
        for promise in promises:
            # Check if promise is active (no start_date = always active, or start date has passed)
            if not promise.start_date or promise.start_date <= ref_time.date():
                report_data[promise.id] = {
                    'text': promise.text.replace('_', ' '),
                    'hours_promised': promise.hours_per_week,
                    'hours_spent': 0.0
                }
                # Map normalized id -> canonical id (first one wins if duplicates exist)
                norm = normalize_promise_id(promise.id)
                canonical_by_norm.setdefault(norm, promise.id)
        
        # Accumulate hours for each promise
        for action in actions:
            if action.at >= week_start and action.at <= week_end:
                canonical = canonical_by_norm.get(normalize_promise_id(action.promise_id))
                if canonical and canonical in report_data:
                    report_data[canonical]['hours_spent'] += action.time_spent
        
        return report_data

    def get_weekly_summary_with_sessions(self, user_id: int, ref_time: datetime, user_timezone: str = "UTC") -> Dict[str, Any]:
        """Get weekly summary data with per-day session breakdown for visualization."""
        # Ensure ref_time is naive (no timezone) for consistent week calculation
        if ref_time.tzinfo is not None:
            ref_time = ref_time.replace(tzinfo=None)
        
        # Get week boundaries
        week_start, week_end = get_week_range(ref_time)
        logger.debug(f"[DEBUG] Week range for {ref_time}: {week_start} to {week_end}")
        
        # Get all promises
        promises = self.promises_repo.list_promises(user_id)
        logger.debug(f"[DEBUG] Found {len(promises)} promises for user {user_id}")
        
        # Get actions from this week
        actions = self.actions_repo.list_actions(user_id, since=week_start)
        logger.debug(f"[DEBUG] Found {len(actions)} actions since {week_start}")
        
        # Initialize report data (keyed by canonical promise.id from storage)
        report_data: Dict[str, Any] = {}
        canonical_by_norm: Dict[str, str] = {}
        for promise in promises:
            # Check if promise is active (no start_date = always active, or start date has passed)
            if not promise.start_date or promise.start_date <= ref_time.date():
                report_data[promise.id] = {
                    'text': promise.text.replace('_', ' '),
                    'hours_promised': promise.hours_per_week,
                    'hours_spent': 0.0,
                    'sessions': []  # List of {'date': date, 'hours': float}
                }
                norm = normalize_promise_id(promise.id)
                canonical_by_norm.setdefault(norm, promise.id)
        
        # Import timezone conversion utilities
        import pytz
        
        # Group actions by promise and date
        actions_by_promise_date: Dict[str, Dict[date, float]] = {}
        actions_in_range = 0
        user_tz_obj = pytz.timezone(user_timezone)
        
        # Get server timezone to convert action times correctly
        server_tz = datetime.now().astimezone().tzinfo
        
        for action in actions:
            # Ensure action.at is naive for comparison
            action_at = action.at
            if action_at.tzinfo is not None:
                action_at = action_at.replace(tzinfo=None)
            
            if week_start <= action_at <= week_end:
                actions_in_range += 1
                canonical = canonical_by_norm.get(normalize_promise_id(action.promise_id))
                if canonical and canonical in report_data:
                    # Convert action datetime from server local time to user's timezone before extracting date
                    # action.at is in server local time (naive) from dt_utc_iso_to_local_naive
                    # We need to: server local -> UTC -> user timezone -> date
                    try:
                        # Treat action_at as server local time
                        action_at_server = action_at.replace(tzinfo=server_tz)
                        # Convert to UTC
                        action_at_utc = action_at_server.astimezone(pytz.UTC)
                        # Convert to user timezone
                        action_at_user_tz = action_at_utc.astimezone(user_tz_obj)
                        # Extract date in user's timezone
                        action_date = action_at_user_tz.date()
                    except Exception as e:
                        logger.warning(f"[DEBUG] Failed to convert action time to user timezone: {e}, using server local date")
                        # Fallback to original behavior
                        action_date = action_at.date()
                    if canonical not in actions_by_promise_date:
                        actions_by_promise_date[canonical] = {}
                    if action_date not in actions_by_promise_date[canonical]:
                        actions_by_promise_date[canonical][action_date] = 0.0
                    actions_by_promise_date[canonical][action_date] += action.time_spent
                else:
                    logger.debug(f"[DEBUG] Action for promise {action.promise_id} (normalized: {normalize_promise_id(action.promise_id)}) not matched to canonical promise. Canonical map: {canonical_by_norm}")
            else:
                logger.debug(f"[DEBUG] Action at {action_at} is outside week range {week_start} to {week_end}")
        
        logger.debug(f"[DEBUG] {actions_in_range} actions in week range, grouped into {len(actions_by_promise_date)} promises")
        
        # Convert to sessions format and accumulate total hours
        for promise_id, date_hours in actions_by_promise_date.items():
            sessions = []
            total_hours = 0.0
            for action_date, hours in sorted(date_hours.items()):
                sessions.append({'date': action_date, 'hours': hours})
                total_hours += hours
            report_data[promise_id]['hours_spent'] = total_hours
            report_data[promise_id]['sessions'] = sessions
        
        return report_data

    def get_promise_summary(self, user_id: int, promise_id: str, ref_time: datetime) -> Dict[str, Any]:
        """Get summary for a specific promise."""
        promise = self.promises_repo.get_promise(user_id, promise_id)
        if not promise:
            return {}
        canonical_promise_id = promise.id
        
        # Get week boundaries
        week_start, week_end = get_week_range(ref_time)
        
        # Get actions for this promise
        all_actions = self.actions_repo.list_actions(user_id)
        promise_actions = [a for a in all_actions if promise_ids_equal(a.promise_id, canonical_promise_id)]
        
        # Calculate weekly hours
        weekly_actions = [a for a in promise_actions if week_start <= a.at <= week_end]
        weekly_hours = sum(a.time_spent for a in weekly_actions)
        
        # Calculate total hours
        total_hours = sum(a.time_spent for a in promise_actions)
        
        # Calculate streak
        streak = self._calculate_streak(promise_actions, ref_time)
        
        return {
            'promise': promise,
            'weekly_hours': weekly_hours,
            'total_hours': total_hours,
            'streak': streak,
            'recent_actions': promise_actions[-3:] if promise_actions else []
        }

    def _calculate_streak(self, actions: list, ref_time: datetime) -> int:
        """Calculate the current streak for a promise."""
        if not actions:
            return 0
        
        # Sort actions by date (most recent first)
        actions.sort(key=lambda a: a.at, reverse=True)
        
        # Get unique dates
        unique_dates = []
        seen_dates = set()
        for action in actions:
            action_date = action.at.date()
            if action_date not in seen_dates:
                unique_dates.append(action_date)
                seen_dates.add(action_date)
        
        if not unique_dates:
            return 0
        
        # Check if the last action was today or yesterday
        current_date = ref_time.date()
        last_action_date = unique_dates[0]
        
        if last_action_date == current_date:
            # Count consecutive days from today backwards
            streak = 0
            expected_date = current_date
            for action_date in unique_dates:
                if action_date == expected_date:
                    streak += 1
                    expected_date -= timedelta(days=1)
                else:
                    break
            return streak
        elif last_action_date == current_date - timedelta(days=1):
            # Count consecutive days from yesterday backwards
            streak = 0
            expected_date = current_date - timedelta(days=1)
            for action_date in unique_dates:
                if action_date == expected_date:
                    streak += 1
                    expected_date -= timedelta(days=1)
                else:
                    break
            return streak
        else:
            # Count negative streak (days since last action)
            days_since = (current_date - last_action_date).days
            return -days_since

    def get_streak_heatmap_data(self, user_id: int, ref_time: datetime) -> Dict[str, Any]:
        """
        Get streak heatmap data for last 4 weeks (28 days) per promise.
        
        Args:
            user_id: User ID
            ref_time: Reference time (typically current time)
        
        Returns:
            Dictionary with promise_id as key and data containing:
            - text: Promise text
            - days: Dict mapping date -> bool (had activity)
            - hours_by_date: Dict mapping date -> float (hours spent)
        """
        # Calculate 4 weeks ago (28 days)
        four_weeks_ago = ref_time - timedelta(days=28)
        
        # Get all promises
        promises = self.promises_repo.list_promises(user_id)
        
        # Get actions from last 4 weeks
        actions = self.actions_repo.list_actions(user_id, since=four_weeks_ago)
        
        # Initialize report data (keyed by canonical promise.id from storage)
        report_data: Dict[str, Any] = {}
        canonical_by_norm: Dict[str, str] = {}
        
        # Get the Monday of the week that contains ref_time
        week_start, _ = get_week_range(ref_time)
        # Calculate the Monday of 4 weeks ago
        four_weeks_monday = week_start - timedelta(days=21)  # 3 weeks back from current week
        
        # Initialize all dates in the 4-week range (Monday to Sunday, 4 weeks)
        all_dates = []
        for week_offset in range(4):
            week_monday = four_weeks_monday + timedelta(days=week_offset * 7)
            for day_offset in range(7):
                all_dates.append(week_monday + timedelta(days=day_offset))
        
        for promise in promises:
            # Check if promise is active
            if not promise.start_date or promise.start_date <= ref_time.date():
                # Initialize all dates as False (no activity)
                days_dict = {d: False for d in all_dates}
                hours_dict = {d: 0.0 for d in all_dates}
                
                report_data[promise.id] = {
                    'text': promise.text.replace('_', ' '),
                    'days': days_dict,
                    'hours_by_date': hours_dict
                }
                norm = normalize_promise_id(promise.id)
                canonical_by_norm.setdefault(norm, promise.id)
        
        # Process actions and mark days with activity
        for action in actions:
            if action.at >= four_weeks_ago:
                canonical = canonical_by_norm.get(normalize_promise_id(action.promise_id))
                if canonical and canonical in report_data:
                    action_date = action.at.date()
                    if action_date in report_data[canonical]['days']:
                        report_data[canonical]['days'][action_date] = True
                        report_data[canonical]['hours_by_date'][action_date] += action.time_spent
        
        return report_data

    async def generate_weekly_visualization_image(self, user_id: int, ref_time: datetime, temp_dir: str = None) -> str:
        """
        Generate weekly visualization image and return path to temp file.
        
        Args:
            user_id: User ID
            ref_time: Reference time for week calculation
            temp_dir: Optional temp directory (defaults to system temp)
        
        Returns:
            Path to generated image file (should be deleted after use)
        """
        engine = (os.environ.get("WEEKLY_VIZ_ENGINE") or "html").strip().lower()
        
        # Get weekly summary with sessions
        summary = self.get_weekly_summary_with_sessions(user_id, ref_time)
        week_start, week_end = get_week_range(ref_time)
        
        # Generate unique temp filename
        if temp_dir is None:
            temp_dir = tempfile.gettempdir()
        
        # Use UUID to ensure unique filename
        unique_id = str(uuid.uuid4())
        image_path = os.path.join(temp_dir, f"weekly_viz_{user_id}_{unique_id}.png")
        
        # Generate visualization
        if engine in ("matplotlib", "mpl", "legacy"):
            from visualisation.vis_rects import generate_weekly_visualization

            generate_weekly_visualization(summary, image_path, width=1200, height=900)
        else:
            try:
                from visualisation.weekly_report_card import render_weekly_report_card_png_async

                await render_weekly_report_card_png_async(
                    summary=summary,
                    output_path=image_path,
                    week_start=week_start,
                    week_end=week_end,
                    width=1200,
                )
            except Exception as e:
                # Any failure in the new HTML/Chromium pipeline should gracefully fallback
                # to the legacy matplotlib visualization to keep /weekly reliable.
                logger.warning(
                    "Weekly HTML visualization failed; falling back to matplotlib treemap. Error: %s",
                    str(e),
                )
                from visualisation.vis_rects import generate_weekly_visualization

                generate_weekly_visualization(summary, image_path, width=1200, height=900)
        
        return image_path

    async def generate_streak_heatmap_image(self, user_id: int, ref_time: datetime, temp_dir: str = None) -> str:
        """
        Generate streak heatmap visualization image and return path to temp file.
        
        Args:
            user_id: User ID
            ref_time: Reference time for heatmap calculation
            temp_dir: Optional temp directory (defaults to system temp)
        
        Returns:
            Path to generated image file (should be deleted after use)
        """
        # Get streak heatmap data
        heatmap_data = self.get_streak_heatmap_data(user_id, ref_time)
        
        # Generate unique temp filename
        if temp_dir is None:
            temp_dir = tempfile.gettempdir()
        
        # Use UUID to ensure unique filename
        unique_id = str(uuid.uuid4())
        image_path = os.path.join(temp_dir, f"streak_heatmap_{user_id}_{unique_id}.png")
        
        # Generate visualization
        try:
            from visualisation.streak_heatmap import render_streak_heatmap_png

            await render_streak_heatmap_png(
                heatmap_data=heatmap_data,
                output_path=image_path,
                ref_time=ref_time,
                width=1400,
            )
        except Exception as e:
            logger.warning(
                "Streak heatmap visualization failed. Error: %s",
                str(e),
            )
            raise
        
        return image_path
