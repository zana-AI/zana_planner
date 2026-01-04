from typing import Dict, Any, List
from datetime import datetime, timedelta, date
import os
import tempfile
import uuid
import logging

from repositories.promises_repo import PromisesRepository
from repositories.actions_repo import ActionsRepository
from repositories.instances_repo import InstancesRepository
from repositories.distractions_repo import DistractionsRepository
from utils.time_utils import get_week_range
from utils.promise_id import normalize_promise_id, promise_ids_equal
from db.sqlite_db import resolve_promise_uuid, connection_for_root


logger = logging.getLogger(__name__)


class ReportsService:
    def __init__(self, promises_repo: PromisesRepository, actions_repo: ActionsRepository, root_dir: str = None):
        self.promises_repo = promises_repo
        self.actions_repo = actions_repo
        self.root_dir = root_dir

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

    def get_weekly_summary_with_sessions(self, user_id: int, ref_time: datetime) -> Dict[str, Any]:
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
        
        # Get instances to check for template-derived promises
        instances_by_promise_uuid: Dict[str, Dict] = {}
        if self.root_dir:
            from repositories.instances_repo import InstancesRepository
            instances_repo = InstancesRepository(self.root_dir)
            user = str(user_id)
            with connection_for_root(self.root_dir) as conn:
                for promise in promises:
                    promise_uuid = resolve_promise_uuid(conn, user, promise.id)
                    if promise_uuid:
                        instance = instances_repo.get_instance_by_promise_uuid(user_id, promise_uuid)
                        if instance:
                            instances_by_promise_uuid[promise_uuid] = instance
        
        # Initialize report data (keyed by canonical promise.id from storage)
        report_data: Dict[str, Any] = {}
        canonical_by_norm: Dict[str, str] = {}
        promise_uuid_by_id: Dict[str, str] = {}
        for promise in promises:
            # Check if promise is active (no start_date = always active, or start date has passed)
            if not promise.start_date or promise.start_date <= ref_time.date():
                user = str(user_id)
                promise_uuid = None
                instance = None
                if self.root_dir:
                    with connection_for_root(self.root_dir) as conn:
                        promise_uuid = resolve_promise_uuid(conn, user, promise.id)
                        if promise_uuid:
                            promise_uuid_by_id[promise.id] = promise_uuid
                            instance = instances_by_promise_uuid.get(promise_uuid)
                
                # Determine metric type and target
                if instance:
                    metric_type = instance['metric_type']
                    target_value = instance['target_value']
                    target_direction = instance['target_direction']
                    template_kind = instance['template_kind']
                else:
                    # Legacy promise: hours-based
                    metric_type = 'hours'
                    target_value = promise.hours_per_week
                    target_direction = 'at_least'
                    template_kind = 'commitment'
                
                report_data[promise.id] = {
                    'text': promise.text.replace('_', ' '),
                    'hours_promised': promise.hours_per_week,  # Keep for backward compat
                    'hours_spent': 0.0,  # Will be updated based on metric_type
                    'sessions': [],  # List of {'date': date, 'hours': float} or {'date': date, 'count': int}
                    'visibility': getattr(promise, 'visibility', 'private'),
                    'recurring': bool(promise.recurring),
                    'metric_type': metric_type,
                    'target_value': target_value,
                    'target_direction': target_direction,
                    'template_kind': template_kind,
                    'achieved_value': 0.0,  # Will be computed
                }
                norm = normalize_promise_id(promise.id)
                canonical_by_norm.setdefault(norm, promise.id)
        
        # Group actions by promise and date
        actions_by_promise_date: Dict[str, Dict[date, Any]] = {}
        actions_in_range = 0
        for action in actions:
            # Ensure action.at is naive for comparison
            action_at = action.at
            if action_at.tzinfo is not None:
                action_at = action_at.replace(tzinfo=None)
            
            if week_start <= action_at <= week_end:
                actions_in_range += 1
                canonical = canonical_by_norm.get(normalize_promise_id(action.promise_id))
                if canonical and canonical in report_data:
                    action_date = action_at.date()
                    if canonical not in actions_by_promise_date:
                        actions_by_promise_date[canonical] = {}
                    if action_date not in actions_by_promise_date[canonical]:
                        actions_by_promise_date[canonical][action_date] = {'hours': 0.0, 'count': 0}
                    
                    # Track both hours and count
                    if action.action == 'log_time':
                        actions_by_promise_date[canonical][action_date]['hours'] += action.time_spent
                    elif action.action == 'checkin':
                        actions_by_promise_date[canonical][action_date]['count'] += 1
                else:
                    logger.debug(f"[DEBUG] Action for promise {action.promise_id} (normalized: {normalize_promise_id(action.promise_id)}) not matched to canonical promise. Canonical map: {canonical_by_norm}")
            else:
                logger.debug(f"[DEBUG] Action at {action_at} is outside week range {week_start} to {week_end}")
        
        logger.debug(f"[DEBUG] {actions_in_range} actions in week range, grouped into {len(actions_by_promise_date)} promises")
        
        # Handle budget templates with distraction_events
        if self.root_dir:
            from repositories.distractions_repo import DistractionsRepository
            distractions_repo = DistractionsRepository(self.root_dir)
            for promise_id, promise_data in report_data.items():
                if promise_data.get('template_kind') == 'budget' and promise_data.get('metric_type') == 'hours':
                    promise_uuid = promise_uuid_by_id.get(promise_id)
                    if promise_uuid:
                        instance = instances_by_promise_uuid.get(promise_uuid)
                        if instance:
                            # Get distraction events for this week
                            distraction_data = distractions_repo.get_weekly_distractions(
                                user_id, week_start, week_end
                            )
                            promise_data['achieved_value'] = distraction_data['total_hours']
                            promise_data['hours_spent'] = distraction_data['total_hours']  # For backward compat
                            # Create sessions from distraction events (simplified: one session per day with hours)
                            # For now, we'll just set total - detailed per-day distraction tracking can be added later
                            promise_data['sessions'] = [{'date': week_start.date(), 'hours': distraction_data['total_hours']}]
        
        # Convert to sessions format and accumulate totals
        for promise_id, date_data in actions_by_promise_date.items():
            promise_data = report_data[promise_id]
            metric_type = promise_data.get('metric_type', 'hours')
            sessions = []
            total_hours = 0.0
            total_count = 0
            
            for action_date, data in sorted(date_data.items()):
                if metric_type == 'count':
                    count = data.get('count', 0)
                    sessions.append({'date': action_date, 'count': count})
                    total_count += count
                else:  # hours
                    hours = data.get('hours', 0.0)
                    sessions.append({'date': action_date, 'hours': hours})
                    total_hours += hours
            
            if metric_type == 'count':
                promise_data['achieved_value'] = float(total_count)
                promise_data['hours_spent'] = 0.0  # Not applicable for count
            else:
                promise_data['achieved_value'] = total_hours
                promise_data['hours_spent'] = total_hours
            
            promise_data['sessions'] = sessions
        
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
