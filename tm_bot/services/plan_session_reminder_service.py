"""Dispatch Telegram reminders for due planned sessions."""

from repositories.plan_sessions_repo import PlanSessionsRepository
from utils.logger import get_logger
from webapp.notifications import send_plan_session_reminder


logger = get_logger(__name__)


class PlanSessionReminderService:
    """Find due planned sessions and send their Telegram reminders."""

    def __init__(self, repo: PlanSessionsRepository | None = None) -> None:
        self.repo = repo or PlanSessionsRepository()

    async def dispatch_due_reminders(
        self,
        bot_token: str,
        lookahead_minutes: int = 1,
        limit: int = 100,
    ) -> int:
        due_sessions = self.repo.list_sessions_needing_reminder(lookahead_minutes=lookahead_minutes)
        sent = 0

        for ps in due_sessions[:limit]:
            plan_session_id = int(ps["id"])
            user_id = int(ps["user_id"])
            try:
                offset = ps.get("reminder_offset_min")
                await send_plan_session_reminder(
                    bot_token=bot_token,
                    user_id=user_id,
                    plan_session_id=plan_session_id,
                    promise_id=ps.get("promise_id") or "",
                    promise_text=ps.get("promise_text") or "Promise",
                    title=ps.get("title"),
                    planned_start=ps.get("planned_start"),
                    planned_duration_min=ps.get("planned_duration_min"),
                    reminder_offset_min=int(10 if offset is None else offset),
                )
                self.repo.mark_plan_session_notified(plan_session_id)
                sent += 1
            except Exception as exc:
                logger.error(
                    "Failed to send planned session reminder %s to user %s: %s",
                    plan_session_id,
                    user_id,
                    exc,
                    exc_info=True,
                )

        return sent
