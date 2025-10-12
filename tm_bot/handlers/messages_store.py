from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


class Language(Enum):
    """Supported languages."""
    EN = "en"
    FR = "fr"
    ES = "fa"
    # DE = "de"


@dataclass
class MessageTemplate:
    """Template for translatable messages."""
    key: str
    default_text: str
    variables: Optional[Dict[str, str]] = None


class MessageTemplateStore:
    """Manages translations and message formatting."""

    def __init__(self, default_language: Language = Language.EN):
        self.default_language = default_language

    def _get_english_translations(self) -> Dict[str, str]:
        """English translations."""
        return {
            # Welcome messages
            "welcome_new": (
                "**Welcome to Zana Planner 👋**\n\n"
                "I help you keep weekly promises with tiny daily check-ins. "
                "It takes about a minute to set up your first promise.\n\n"
                "**How it works**\n"
                "1) Create a promise (what you’ll commit to each week)\n"
                "2) Choose hours per week\n"
                # "3) (Optional) Set an evening reminder time\n\n"
                "**Examples**\n"
                "• *I'd like to study English 6 hours per week*\n"
                "• *I'm gonna Deep work 30 hours per week*\n\n"
                "Reply with your promise in plain words (e.g., *“Exercise 3 hours per week”*)."
                " Feel free to use whatever language or style you like."
            ),
            "welcome_return": (
                "Hi! Welcome back 👋\n\n"
                "Would you like to define a new promise or check your existing progress?"
            ),

            # Commands
            "no_promises": "You have no promises. You want to add one? For example, you could promise to 'deep work 6 hours a day, 5 days a week', 'spend 2 hours a week on playing guitar.'",
            "promises_list_header": "Your promises:",
            "promise_item": "* {id}: {text}",

            # Nightly reminders
            "nightly_header": "🌙 *Nightly reminders*",
            "nightly_header_with_more": "🌙 *Nightly reminders*\n_{date}_\nHere are today's top 3. Tap \"Show more\" for additional suggestions.",
            "nightly_question": "How much time did you spend today on *{promise_text}*?",
            "show_more_button": "Show more ({count})",
            "thats_all": "✅ That's all for today.",

            # Morning reminders
            "morning_header": "☀️ *{date} Morning Focus*\nHere are the top 3 to prioritize today. Pick a quick time or adjust, then get rolling.",
            "morning_question": "🌸 What about *{promise_text}* today? Ready to start?",

            # Weekly reports
            "weekly_header": "Weekly: {date_range}",
            "weekly_no_data": "No data available for this week.",

            # Timezone
            "timezone_invalid": "Invalid timezone. Example: /settimezone Europe/Paris",
            "timezone_set": "Timezone set to {timezone}",
            "timezone_location_request": "Please share your location once so I can set your timezone.",
            "timezone_location_failed": "Sorry, I couldn't detect your timezone. You can set it manually, e.g. /settimezone Europe/Paris",
            "timezone_location_success": "Timezone set to {timezone}. I'll schedule reminders in your local time.",

            # Pomodoro
            "pomodoro_start": "Pomodoro Timer: 25:00",
            "pomodoro_paused": "Pomodoro Timer Paused.",
            "pomodoro_stopped": "Pomodoro Timer Stopped.",
            "pomodoro_finished": "Pomodoro Timer (25min) Finished! 🎉",
            "pomodoro_break": "Time's up! Take a break or start another session.",

            # Session management
            "session_started": "Timer started",
            "session_paused": "Session paused",
            "session_resumed": "Session resumed",
            "session_finished": "Session finished",
            "session_logged": "Logged {time} for *{promise_id}*. ✅",
            "session_skipped": "Noted. We'll skip this one today. ✅",
            "session_snoozed": "#{promise_id} snoozed for {minutes}m. ⏰",
            "session_ready": "*{promise_text}* — ready to start?",

            # Time tracking
            "time_selected": "{time} selected",
            "time_spent": "[{date}] spent *{time}* on #{promise_id}:\n{promise_text}",
            "time_added": "Added {time}",
            "time_snoozed": "Snoozed {minutes}m",

            # Promise management
            "promise_remind_next_week": "#{promise_id} will be silent until monday.",
            "promise_deleted": "Promise deleted",
            "promise_report": "Promise report generated",

            # Zana insights
            "zana_insights": "Insights from Zana:\n{insights}",
            "zana_no_promises": "You have no promises to report on.",

            # Error messages
            "error_invalid_input": "⚠️ Invalid input: {error}",
            "error_general": "❌ Sorry, I couldn't complete this action. Please try again.\nError: {error}",
            "error_unexpected": "🔧 Something went wrong. Please try again later. Error: {error}",
            "error_llm_trouble": "I'm having trouble understanding that. Could you rephrase?",
            "error_llm_parsing": "Error parsing response",
            "error_llm_unexpected": "Something went wrong. Error: {error}",

            # Keyboard buttons
            "btn_start": "Start",
            "btn_pause": "Pause",
            "btn_stop": "Stop",
            "btn_resume": "Resume",
            "btn_finish": "Finish",
            "btn_refresh": "🔄 Refresh",
            "btn_show_more": "Show more promises",
            "btn_log_time": "Log time for #{promise_id}",
            "btn_none": "🙅 None",
            "btn_skip_week": "⏭️ Skip (wk)",
            "btn_not_today": "Not today 🙅",
            "btn_more": "More…",
            "btn_yes_delete": "Yes (delete)",
            "btn_no_cancel": "No (cancel)",
            "btn_looks_right": "Looks right ✅ ({time})",
            "btn_adjust": "Adjust…",
            "btn_share_location": "Share location",

            # Time formatting
            "time_none": "None",
            "time_minutes": "{minutes}m",
            "time_hours": "{hours}h",
            "time_hours_minutes": "{hours}h {minutes}m",
        }

    def get_message(self, key: str, language: Optional[Language] = None, **kwargs) -> str:
        """Get translated message with variable substitution."""
        lang = language or self.default_language
        # translations = self.translations.get(lang, self.translations[self.default_language])

        message = self._get_english_translations().get(key, key)

        # Substitute variables
        if kwargs:
            try:
                message = message.format(**kwargs)
            except KeyError as e:
                # If a variable is missing, log and return the message as-is
                import logging
                logging.warning(f"Missing variable {e} for message key '{key}' in language {lang.value}")

        return message

    def get_user_language(self, user_id: int) -> Language:
        """Get user's preferred language. For now, returns default language."""
        # TODO: Implement user language preference storage in settings repository
        return self.default_language


# Global instance
_translation_manager = MessageTemplateStore()


def get_message(key: str, language: Optional[Language] = None, **kwargs) -> str:
    """Convenience function to get translated message."""
    return _translation_manager.get_message(key, language, **kwargs)


def get_user_language(user_id: int) -> Language:
    """Convenience function to get user's language."""
    return _translation_manager.get_user_language(user_id)
