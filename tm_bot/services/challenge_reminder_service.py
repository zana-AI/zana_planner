"""
Daily "your quiz is ready" reminder for challenges.

Once a day, at each challenge's `reminder_local_time` (HH:MM, UTC for v1), DM every active
subscriber who still has a quiz due today, with a button that opens the Mini App straight into
play. Mirrors the plan-session reminder sweeper; gated behind an env flag so it stays off in dev.

Per-user timezone scheduling is a refinement (v1 treats reminder_local_time as UTC HH:MM).
"""

import asyncio
import os
from datetime import datetime, timezone

from utils.logger import get_logger

logger = get_logger(__name__)

_ENABLED_VALUES = {"1", "true", "yes", "on"}


def is_challenge_reminder_enabled() -> bool:
    return os.getenv("WEBAPP_CHALLENGE_REMINDER_SWEEPER", "0").strip().lower() in _ENABLED_VALUES


class ChallengeReminderService:
    def __init__(self, bot_token: str | None, miniapp_url: str | None = None) -> None:
        self.bot_token = bot_token
        self.miniapp_url = (miniapp_url or os.getenv("MINIAPP_URL", "https://xaana.club")).rstrip("/")
        # In-memory dedup so a challenge isn't reminded twice within the same minute/day.
        self._sent: set[tuple[str, str, str]] = set()  # (date, challenge_id, user_id)
        self._task: asyncio.Task | None = None

    def find_due(self, now_utc: datetime) -> list[dict]:
        """Return [{user_id, challenge_id, title, source_key}] to remind right now."""
        from repositories.challenges_repo import ChallengesRepository

        repo = ChallengesRepository()
        hhmm = now_utc.strftime("%H:%M")
        today = now_utc.strftime("%Y-%m-%d")
        due: list[dict] = []
        for ch in repo.challenges_with_reminder_at(hhmm):
            cid = ch["challenge_id"]
            for uid in repo.list_subscribed_user_ids(cid):
                if (today, cid, uid) in self._sent:
                    continue
                # Only nudge users who still have a quiz to do today.
                if repo.get_due_deck(cid, int(uid)) is None:
                    continue
                due.append({"user_id": uid, "challenge_id": cid, "title": ch["title"], "source_key": ch.get("source_key")})
        return due

    async def send_due(self, now_utc: datetime | None = None) -> int:
        if not self.bot_token:
            return 0
        from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

        now_utc = now_utc or datetime.now(timezone.utc)
        today = now_utc.strftime("%Y-%m-%d")
        due = self.find_due(now_utc)
        if not due:
            return 0

        bot = Bot(token=self.bot_token)
        sent = 0
        for item in due:
            try:
                play_url = f"{self.miniapp_url}/challenges/{item['challenge_id']}/play"
                keyboard = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("▶️ Play today's quiz", web_app=WebAppInfo(url=play_url))]]
                )
                await bot.send_message(
                    chat_id=int(item["user_id"]),
                    text=f"📝 Your <b>{item['title']}</b> quiz is ready for today!",
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
                self._sent.add((today, item["challenge_id"], str(item["user_id"])))
                sent += 1
            except Exception as e:  # one bad send must not stop the batch
                logger.warning("Challenge reminder send failed for %s/%s: %s", item["challenge_id"], item["user_id"], e)
        return sent

    async def start(self) -> None:
        if not is_challenge_reminder_enabled():
            logger.info("Challenge reminder sweeper disabled (WEBAPP_CHALLENGE_REMINDER_SWEEPER=0)")
            return
        if self._task is not None:
            return

        async def _loop() -> None:
            logger.info("✓ Started challenge reminder sweeper (checks every 60s)")
            while True:
                try:
                    now = datetime.now(timezone.utc)
                    # Drop yesterday's dedup entries so today can fire.
                    today = now.strftime("%Y-%m-%d")
                    self._sent = {s for s in self._sent if s[0] == today}
                    await self.send_due(now)
                except Exception as e:
                    logger.error("Challenge reminder sweeper error: %s", e, exc_info=True)
                await asyncio.sleep(60)

        self._task = asyncio.create_task(_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
