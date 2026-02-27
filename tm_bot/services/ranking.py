from typing import List, Tuple
import random
from collections import defaultdict
from datetime import datetime, timedelta

from models.models import Promise
from repositories.promises_repo import PromisesRepository
from repositories.actions_repo import ActionsRepository
from repositories.settings_repo import SettingsRepository


class RankingService:
    def __init__(self, promises_repo: PromisesRepository, actions_repo: ActionsRepository, settings_repo: SettingsRepository):
        self.promises_repo = promises_repo
        self.actions_repo = actions_repo
        self.settings_repo = settings_repo

    def score_promises_for_today(self, user_id: int, now: datetime) -> List[Tuple[Promise, float]]:
        """
        Score promises for today using rule-based signals.
        Higher scores indicate higher priority.
        """
        promises = self.promises_repo.list_promises(user_id)
        actions = self.actions_repo.list_actions(user_id)

        # Filter active promises (must have started and not ended)
        active_promises = [
            p for p in promises
            if p.start_date and p.start_date <= now.date()
            and (not p.end_date or p.end_date >= now.date())
        ]

        scored_promises = []
        for promise in active_promises:
            score = self._calculate_promise_score(promise, actions, now)
            scored_promises.append((promise, score))

        return scored_promises

    def _calculate_promise_score(self, promise: Promise, actions: List, now: datetime) -> float:
        """Calculate score for a single promise."""
        score = 0.0

        # Signal 1: Motivation-adjusted weekly deficit
        weekly_deficit = self._get_motivation_adjusted_deficit(promise, actions, now)
        score += weekly_deficit * 2.5  # Weight: 2.5

        # Signal 2: Weekday affinity (historically worked on this day?)
        weekday_affinity = self._get_weekday_affinity(promise, actions, now)
        score += weekday_affinity * 2.0  # Weight: 2.0

        # Signal 3: Recency decay (not touched in N days)
        recency_decay = self._get_recency_decay(promise, actions, now)
        score += recency_decay * 1.5  # Weight: 1.5

        # Signal 4: Touched today penalty (small penalty for already worked on)
        touched_today_penalty = self._get_touched_today_penalty(promise, actions, now)
        score -= touched_today_penalty * 0.5  # Weight: -0.5

        # Signal 5: Future opportunity surplus
        # If the task has strong affinity on upcoming days it can wait — discount today.
        # If there are no good upcoming days, no penalty → raise relative urgency.
        future_surplus = self._get_future_opportunity_surplus(promise, actions, now)
        score -= future_surplus * 1.5  # Weight: -1.5

        return score

    # ------------------------------------------------------------------
    # Signal helpers
    # ------------------------------------------------------------------

    def _get_weekday_affinity(self, promise: Promise, actions: List, now: datetime) -> float:
        """How strongly this promise is associated with today's weekday.

        Returns 0-3.  A promise the user always works on Fridays gets ~3 on a
        Friday; one they never touch on Fridays gets 0.
        """
        today_name = now.strftime('%A')
        promise_actions = [a for a in actions if a.promise_id == promise.id]
        if not promise_actions:
            return 0.0

        # Count distinct dates per weekday for this promise
        day_dates: dict = defaultdict(set)
        for a in promise_actions:
            day_dates[a.at.strftime('%A')].add(a.at.date())

        total_distinct_days = sum(len(dates) for dates in day_dates.values())
        if total_distinct_days == 0:
            return 0.0

        today_count = len(day_dates.get(today_name, set()))
        ratio = today_count / total_distinct_days  # 0-1 range
        num_weekdays_active = len(day_dates)
        # Boost when activity is concentrated on fewer days (specialist promise).
        # e.g. if a user only works on this promise 2 days/week, each matching
        # day should be worth more than if they spread across 7 days.
        return min(3.0, ratio * 3.0 * num_weekdays_active)

    def _get_motivation_adjusted_deficit(self, promise: Promise, actions: List, now: datetime) -> float:
        """Weekly deficit, dampened when the user historically ignores a promise.

        Pure deficit = max(0, expected_hours - hours_spent_this_week).
        Motivation factor = avg_weekly_hours_past_4wks / hours_per_week.
        Final = deficit * clamp(motivation, 0.15, 1.0)

        A promise with 0 target hours and 0 past activity still scores low but
        not zero (floor at 0.15) so it eventually surfaces.
        """
        tz = now.tzinfo

        def as_tz(dt: datetime) -> datetime:
            if tz is None:
                return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt
            return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt.astimezone(tz)

        # --- current-week deficit ---
        monday = now - timedelta(days=now.weekday())
        week_start = monday.replace(hour=3, minute=0, second=0, microsecond=0)
        if now < week_start:
            week_start -= timedelta(days=7)

        now_local = as_tz(now)
        week_start_local = as_tz(week_start)

        weekly_actions = [
            a for a in actions
            if a.promise_id == promise.id and week_start_local <= as_tz(a.at) <= now_local
        ]
        hours_spent = sum(float(getattr(a, "time_spent", 0.0) or 0.0) for a in weekly_actions)

        week_seconds = 7 * 24 * 3600
        progress = (now_local - week_start_local).total_seconds() / week_seconds
        progress = max(0.0, min(1.0, progress))

        hpw = float(getattr(promise, "hours_per_week", 0.0) or 0.0)
        expected_hours = hpw * progress
        raw_deficit = max(0.0, expected_hours - hours_spent)

        # --- motivation factor: avg weekly hours over past 4 weeks ---
        four_wk_start = week_start_local - timedelta(weeks=4)
        past_actions = [
            a for a in actions
            if a.promise_id == promise.id and four_wk_start <= as_tz(a.at) < week_start_local
        ]
        past_hours = sum(float(getattr(a, "time_spent", 0.0) or 0.0) for a in past_actions)
        avg_weekly_past = past_hours / 4.0

        if hpw > 0:
            motivation = avg_weekly_past / hpw
        else:
            # check-based / no target — use raw activity presence
            motivation = min(1.0, avg_weekly_past) if avg_weekly_past > 0 else 0.15

        motivation = max(0.15, min(1.0, motivation))
        return raw_deficit * motivation

    def _get_recency_decay(self, promise: Promise, actions: list, now: datetime) -> float:
        """Calculate recency decay score (higher if not touched recently)."""
        promise_actions = [a for a in actions if a.promise_id == promise.id]
        if not promise_actions:
            return 3.0  # never worked on -> high priority

        tz = now.tzinfo

        def as_tz(dt: datetime) -> datetime:
            if tz is None:
                return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt
            return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt.astimezone(tz)

        now_local = as_tz(now)
        most_recent = max(promise_actions, key=lambda a: as_tz(a.at))
        last_at_local = as_tz(most_recent.at)

        delta_days = max(0, (now_local.date() - last_at_local.date()).days)

        if delta_days == 0:
            return 0.0
        elif delta_days == 1:
            return 1.0
        elif delta_days <= 3:
            return 2.0
        else:
            return min(3.0, delta_days * 0.5)

    def _get_future_opportunity_surplus(self, promise: Promise, actions: List, now: datetime) -> float:
        """How much opportunity this promise has in the NEXT 6 days.

        Returns 0-1.  A promise the user historically works on most of the
        coming week scores near 1; one they only work on today — or rarely
        at all — scores near 0.

        Applied with a negative weight: high surplus → discount today so the
        task surfaces naturally on its prime upcoming day instead.
        """
        promise_actions = [a for a in actions if a.promise_id == promise.id]
        if not promise_actions:
            return 0.0

        day_dates: dict = defaultdict(set)
        for a in promise_actions:
            day_dates[a.at.strftime('%A')].add(a.at.date())

        total_distinct_days = sum(len(dates) for dates in day_dates.values())
        if total_distinct_days == 0:
            return 0.0

        num_weekdays_active = len(day_dates)
        future_affinity_sum = 0.0
        for offset in range(1, 7):  # next 6 days
            future_day_name = (now + timedelta(days=offset)).strftime('%A')
            count = len(day_dates.get(future_day_name, set()))
            ratio = count / total_distinct_days
            # same raw formula as _get_weekday_affinity, then normalize to 0-1
            raw = min(3.0, ratio * 3.0 * num_weekdays_active)
            future_affinity_sum += raw / 3.0  # each day contributes 0-1

        # max sum = 6 (every upcoming day perfect). Divide by 3 so that having
        # strong affinity on ≥3 out of 6 upcoming days saturates at 1.0.
        return min(1.0, future_affinity_sum / 3.0)

    def _get_touched_today_penalty(self, promise: Promise, actions: List, now: datetime) -> float:
        """Calculate penalty for already working on this promise today."""
        today = now.date()
        today_actions = [
            a for a in actions
            if a.promise_id == promise.id and a.at.date() == today
        ]
        if not today_actions:
            return 0.0
        return 1.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def top_n(self, user_id: int, now: datetime, n: int = 3) -> List[Promise]:
        """Return top *n* promises for today.

        Slots 1-2: highest scoring promises (deterministic).
        Slot 3+: weighted-random pick among remaining promises, favouring
        lower-commitment tasks to encourage variety / discovery.
        """
        scores = self.score_promises_for_today(user_id, now)
        if not scores:
            return []
        sorted_all = sorted(scores, key=lambda t: t[1], reverse=True)

        if n <= 2 or len(sorted_all) <= n:
            return [p for p, _ in sorted_all[:n]]

        # Deterministic top 2
        top2 = sorted_all[:2]
        remaining = sorted_all[2:]

        # Weighted-random pick for slot 3+: score + bonus for low-commitment tasks
        picks: List[Tuple[Promise, float]] = []
        for _ in range(n - 2):
            if not remaining:
                break
            weights = []
            for promise, sc in remaining:
                hpw = float(getattr(promise, 'hours_per_week', 0.0) or 0.0)
                # Low-effort bonus: inversely proportional to weekly hours (capped)
                low_effort_bonus = max(0.0, 3.0 - hpw) * 0.5
                w = max(0.01, sc + low_effort_bonus + 0.5)  # baseline 0.5 so everyone has a chance
                weights.append(w)
            chosen_idx = random.choices(range(len(remaining)), weights=weights, k=1)[0]
            picks.append(remaining.pop(chosen_idx))

        result = top2 + picks
        return [p for p, _ in result]
