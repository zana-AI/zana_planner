"""
Converts platform-agnostic Keyboard objects to Slack Block Kit action blocks.

Each row becomes a Block Kit actions block with button elements.
URL buttons become link_button elements; callback_data becomes the action_id.
"""

from typing import Any, List

from ..interfaces import IKeyboardBuilder
from ..types import Keyboard, KeyboardButton


class SlackKeyboardAdapter(IKeyboardBuilder):
    """Converts Keyboard → Slack Block Kit blocks list."""

    def build_keyboard(self, keyboard: Keyboard) -> List[dict]:
        """Return a list of Slack Block Kit blocks (actions blocks)."""
        blocks: List[dict] = []
        for row in keyboard.buttons:
            elements = [self._button_element(btn) for btn in row]
            if elements:
                blocks.append({"type": "actions", "elements": elements})
        return blocks

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _button_element(btn: KeyboardButton) -> dict:
        if btn.url:
            return {
                "type": "button",
                "text": {"type": "plain_text", "text": btn.text, "emoji": True},
                "url": btn.url,
                "action_id": f"url_{btn.text[:30].replace(' ', '_')}",
            }
        # callback_data becomes the action_id so interactions can be routed
        return {
            "type": "button",
            "text": {"type": "plain_text", "text": btn.text, "emoji": True},
            "action_id": btn.callback_data or btn.text[:30],
            "value": btn.callback_data or "",
        }
