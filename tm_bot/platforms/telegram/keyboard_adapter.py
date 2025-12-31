"""
Telegram keyboard adapter - converts platform-agnostic keyboards to Telegram format.
"""

from typing import List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from ..types import Keyboard, KeyboardButton
from ..interfaces import IKeyboardBuilder


class TelegramKeyboardAdapter(IKeyboardBuilder):
    """Converts platform-agnostic Keyboard to Telegram InlineKeyboardMarkup."""
    
    def build_keyboard(self, keyboard: Keyboard) -> InlineKeyboardMarkup:
        """Convert a platform-agnostic Keyboard to Telegram InlineKeyboardMarkup."""
        if not keyboard or not keyboard.buttons:
            return None

        telegram_buttons = []
        for row in keyboard.buttons:
            telegram_row = []
            for button in row:
                if button.web_app_url:
                    telegram_button = InlineKeyboardButton(
                        text=button.text,
                        web_app=WebAppInfo(url=button.web_app_url)
                    )
                elif button.url:
                    telegram_button = InlineKeyboardButton(
                        text=button.text,
                        url=button.url
                    )
                elif button.callback_data:
                    telegram_button = InlineKeyboardButton(
                        text=button.text,
                        callback_data=button.callback_data
                    )
                else:
                    continue  # Skip invalid buttons
                telegram_row.append(telegram_button)

            if telegram_row:  # Only add non-empty rows
                telegram_buttons.append(telegram_row)

        return InlineKeyboardMarkup(telegram_buttons) if telegram_buttons else None

