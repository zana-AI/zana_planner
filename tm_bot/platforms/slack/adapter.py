"""
Slack platform adapter.

Implements IPlatformAdapter for Slack.  A single instance is created per
club bot token — or a shared instance is used when a central app-level token
is configured via the SLACK_BOT_TOKEN env var.
"""

from typing import Callable, Optional

from ..interfaces import (
    IPlatformAdapter,
    IResponseService,
    IJobScheduler,
    IKeyboardBuilder,
    IMessageHandler,
    ICallbackHandler,
)
from .keyboard_adapter import SlackKeyboardAdapter
from .response_service import SlackResponseService
from .scheduler import SlackJobScheduler
from utils.logger import get_logger

logger = get_logger(__name__)


class SlackPlatformAdapter(IPlatformAdapter):
    """Slack implementation of IPlatformAdapter."""

    def __init__(self, bot_token: str) -> None:
        self._response_service: IResponseService = SlackResponseService(bot_token)
        self._job_scheduler: IJobScheduler = SlackJobScheduler()
        self._keyboard_builder: IKeyboardBuilder = SlackKeyboardAdapter()

    # ------------------------------------------------------------------
    # IPlatformAdapter properties
    # ------------------------------------------------------------------

    @property
    def response_service(self) -> IResponseService:
        return self._response_service

    @property
    def job_scheduler(self) -> IJobScheduler:
        return self._job_scheduler

    @property
    def keyboard_builder(self) -> IKeyboardBuilder:
        return self._keyboard_builder

    # ------------------------------------------------------------------
    # Handler registration (no-ops for now; Slack events come via webhook)
    # ------------------------------------------------------------------

    def register_message_handler(self, handler: IMessageHandler) -> None:
        logger.info("[Slack] Message handler registered (webhook-driven)")

    def register_callback_handler(self, handler: ICallbackHandler) -> None:
        logger.info("[Slack] Callback handler registered (webhook-driven)")

    def register_command_handler(self, command: str, handler: Callable) -> None:
        logger.info("[Slack] Command handler registered: /%s (webhook-driven)", command)

    async def start(self) -> None:
        logger.info("[Slack] Adapter started (webhook mode — no polling)")

    async def stop(self) -> None:
        logger.info("[Slack] Adapter stopped")

    def get_user_info(self, user_id: int) -> dict:
        return {"user_id": user_id, "platform": "slack"}
