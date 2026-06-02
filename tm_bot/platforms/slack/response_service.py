"""
Slack implementation of IResponseService.

Sends messages via the Slack Web API (slack-sdk).  Each club carries its own
bot token so multi-workspace installs are supported without a central token.
"""

from typing import Any, Optional

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from ..interfaces import IResponseService
from ..types import Keyboard
from .keyboard_adapter import SlackKeyboardAdapter
from utils.logger import get_logger

logger = get_logger(__name__)


class SlackResponseService(IResponseService):
    """IResponseService backed by the Slack Web API."""

    def __init__(self, bot_token: str) -> None:
        self._client = WebClient(token=bot_token)
        self._keyboard_adapter = SlackKeyboardAdapter()

    # ------------------------------------------------------------------
    # Core send helpers
    # ------------------------------------------------------------------

    async def send_text(
        self,
        user_id: int,
        chat_id: int,
        text: str,
        keyboard: Optional[Keyboard] = None,
        parse_mode: Optional[str] = None,
        reply_to_message_id: Optional[int] = None,
        disable_web_page_preview: bool = False,
    ) -> Optional[Any]:
        channel = str(chat_id)
        blocks = self._keyboard_adapter.build_keyboard(keyboard) if keyboard else []
        try:
            response = self._client.chat_postMessage(
                channel=channel,
                text=text,
                blocks=blocks or None,
            )
            return response
        except SlackApiError as exc:
            logger.warning("[Slack] chat_postMessage failed for channel %s: %s", channel, exc)
            return None

    async def send_photo(
        self,
        user_id: int,
        chat_id: int,
        photo: Any,
        caption: Optional[str] = None,
        keyboard: Optional[Keyboard] = None,
        parse_mode: Optional[str] = None,
    ) -> Optional[Any]:
        channel = str(chat_id)
        blocks: list = []
        if caption:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": caption}})
        if keyboard:
            blocks.extend(self._keyboard_adapter.build_keyboard(keyboard))
        try:
            if isinstance(photo, (str, bytes)):
                response = self._client.files_upload_v2(
                    channel=channel,
                    content=photo if isinstance(photo, bytes) else None,
                    file=photo if isinstance(photo, str) else None,
                    initial_comment=caption or "",
                )
            else:
                response = self._client.chat_postMessage(
                    channel=channel,
                    text=caption or "",
                    blocks=blocks or None,
                )
            return response
        except SlackApiError as exc:
            logger.warning("[Slack] send_photo failed for channel %s: %s", channel, exc)
            return None

    async def send_voice(
        self,
        user_id: int,
        chat_id: int,
        voice: Any,
    ) -> Optional[Any]:
        channel = str(chat_id)
        try:
            response = self._client.files_upload_v2(
                channel=channel,
                content=voice if isinstance(voice, bytes) else None,
                file=voice if isinstance(voice, str) else None,
                filename="voice.ogg",
            )
            return response
        except SlackApiError as exc:
            logger.warning("[Slack] send_voice failed for channel %s: %s", channel, exc)
            return None

    async def edit_message(
        self,
        user_id: int,
        chat_id: int,
        message_id: int,
        text: str,
        keyboard: Optional[Keyboard] = None,
        parse_mode: Optional[str] = None,
    ) -> Optional[Any]:
        """Edit a previously posted message. message_id is the Slack message ts."""
        channel = str(chat_id)
        ts = str(message_id)
        blocks = self._keyboard_adapter.build_keyboard(keyboard) if keyboard else []
        try:
            response = self._client.chat_update(
                channel=channel,
                ts=ts,
                text=text,
                blocks=blocks or None,
            )
            return response
        except SlackApiError as exc:
            logger.warning("[Slack] chat_update failed for channel %s ts %s: %s", channel, ts, exc)
            return None

    async def delete_message(
        self,
        chat_id: int,
        message_id: int,
    ) -> bool:
        channel = str(chat_id)
        ts = str(message_id)
        try:
            self._client.chat_delete(channel=channel, ts=ts)
            return True
        except SlackApiError as exc:
            logger.warning("[Slack] chat_delete failed for channel %s ts %s: %s", channel, ts, exc)
            return False

    def log_user_message(
        self,
        user_id: int,
        content: str,
        message_id: Optional[int] = None,
        chat_id: Optional[int] = None,
    ) -> None:
        pass
