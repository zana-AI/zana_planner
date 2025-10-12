"""
Callback handlers for the Telegram bot.
Handles all callback query processing from inline keyboards.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from i18n.translations import get_message, get_user_language, Language
from services.planner_api_adapter import PlannerAPIAdapter
from models.models import Action
from utils.time_utils import beautify_time, round_time
from ui.keyboards import (
    time_options_kb, session_running_kb, session_paused_kb, 
    session_finish_confirm_kb, session_adjust_kb, preping_kb
)
from cbdata import encode_cb, decode_cb

logger = logging.getLogger(__name__)


class CallbackHandlers:
    """Handles all callback query processing."""
    
    def __init__(self, plan_keeper: PlannerAPIAdapter, application):
        self.plan_keeper = plan_keeper
        self.application = application
    
    def get_user_timezone(self, user_id: int) -> str:
        """Get user timezone using the settings repository."""
        settings = self.plan_keeper.settings_repo.get_settings(user_id)
        return settings.timezone
    
    def _get_user_now(self, user_id: int):
        """Return (now_in_user_tz, tzname)."""
        from zoneinfo import ZoneInfo
        tzname = self.get_user_timezone(user_id) or "UTC"
        return datetime.now(ZoneInfo(tzname)), tzname
    
    @staticmethod
    def _hours_per_week_of(promise) -> float:
        """Extract hours_per_week whether promise is a dict or a dataclass."""
        try:
            return float(getattr(promise, "hours_per_week"))
        except Exception:
            return float((promise or {}).get("hours_per_week", 0.0) or 0.0)
    
    def _last_hours_or(self, user_id: int, promise_id: str, fallback: float) -> float:
        """Get last hours spent or fallback value."""
        last = self.plan_keeper.get_last_action_on_promise(user_id, promise_id)
        try:
            return float(getattr(last, "time_spent", fallback) or fallback)
        except Exception:
            return fallback
    
    def _schedule_one_pre_ping(self, user_id: int, promise_id: str, when_dt: datetime):
        """Schedule a single pre-ping message."""
        name = f"preping-{user_id}-{promise_id}-{int(when_dt.timestamp())}"
        # remove any previous job with the same name to keep idempotent
        for j in self.application.job_queue.get_jobs_by_name(name):
            j.schedule_removal()
        self.application.job_queue.run_once(
            self.pre_ping_one, when=when_dt,
            data={"user_id": user_id, "promise_id": promise_id},
            name=name,
        )
    
    def _schedule_session_ticker(self, sess):
        """Schedule session ticker. TODO: implement later."""
        return
    
    def _stop_ticker(self, session_id: str):
        """Stop session ticker. TODO: implement later."""
        return
    
    def _schedule_session_resume(self, user_id: int, session_id: str, when_dt: datetime):
        """Schedule session resume. TODO: implement later."""
        return
    
    def _session_text(self, sess, elapsed: str) -> str:
        """Generate session text."""
        return (f"⏱ *Session for #{sess.promise_id}: {self.plan_keeper.promises_repo.get_promise(sess.user_id, sess.promise_id).text}*"
                f"\nStarted {sess.started_at.strftime('%H:%M')} | Elapsed: {elapsed}")
    
    def _session_effective_hours(self, sess) -> float:
        """Calculate effective hours for session. TODO: implement."""
        return 0.5  # placeholder
    
    async def handle_promise_callback(self, update: Update, context: CallbackContext) -> None:
        """Handle all callback queries from inline keyboards."""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        user_lang = get_user_language(user_id)
        
        # Parse callback data
        cb = decode_cb(query.data)
        action = cb.get("a")
        promise_id = cb.get("p")
        value = cb.get("v")
        session_id = cb.get("s")
        minutes = cb.get("m")
        current_s = cb.get("c")
        
        # Route to specific handlers
        if action == "pomodoro_start":
            await self._handle_pomodoro_start(query, context)
        elif action == "pomodoro_pause":
            await self._handle_pomodoro_pause(query, user_lang)
        elif action == "pomodoro_stop":
            await self._handle_pomodoro_stop(query, user_lang)
        elif action == "remind_next_week":
            await self._handle_remind_next_week(query, promise_id, user_lang)
        elif action == "delete_promise":
            await self._handle_delete_promise(query, promise_id)
        elif action == "confirm_delete":
            await self._handle_confirm_delete(query, promise_id, user_lang)
        elif action == "cancel_delete":
            await self._handle_cancel_delete(query)
        elif action == "report_promise":
            await self._handle_report_promise(query, promise_id, user_lang)
        elif action == "update_time_spent":
            await self._handle_update_time_spent(query, promise_id, value, current_s, user_lang)
        elif action == "time_spent":
            await self._handle_time_spent(query, promise_id, value, user_lang)
        elif action == "show_more":
            await self._handle_show_more(query, context, cb, user_lang)
        elif action == "preping_start":
            await self._handle_preping_start(query, promise_id)
        elif action == "preping_skip":
            await self._handle_preping_skip(query, promise_id, user_lang)
        elif action == "preping_snooze":
            await self._handle_preping_snooze(query, promise_id, minutes, user_lang)
        elif action == "open_time":
            await self._handle_open_time(query, promise_id)
        elif action == "session_pause":
            await self._handle_session_pause(query, session_id)
        elif action == "session_resume":
            await self._handle_session_resume(query, session_id)
        elif action == "session_plus":
            await self._handle_session_plus(query, session_id, value, user_lang)
        elif action == "session_snooze":
            await self._handle_session_snooze(query, session_id, minutes, user_lang)
        elif action == "session_finish_open":
            await self._handle_session_finish_open(query, session_id)
        elif action == "session_finish_confirm":
            await self._handle_session_finish_confirm(query, session_id, value, user_lang)
        elif action == "session_adjust_open":
            await self._handle_session_adjust_open(query, session_id, value)
        elif action == "session_adjust_set":
            await self._handle_session_adjust_set(query, session_id, value, user_lang)
        else:
            logger.warning(f"Unknown callback action: {action}")
    
    async def _handle_pomodoro_start(self, query, context):
        """Handle pomodoro timer start."""
        await self.start_pomodoro_timer(query, context)
    
    async def _handle_pomodoro_pause(self, query, user_lang: Language):
        """Handle pomodoro timer pause."""
        message = get_message("pomodoro_paused", user_lang)
        await query.edit_message_text(text=message, parse_mode='Markdown')
    
    async def _handle_pomodoro_stop(self, query, user_lang: Language):
        """Handle pomodoro timer stop."""
        message = get_message("pomodoro_stopped", user_lang)
        await query.edit_message_text(text=message, parse_mode='Markdown')
    
    async def _handle_remind_next_week(self, query, promise_id: str, user_lang: Language):
        """Handle remind next week action."""
        next_monday = (datetime.now() + timedelta(days=(7 - datetime.now().weekday()))).date()
        self.plan_keeper.update_promise_start_date(query.from_user.id, promise_id, next_monday)
        message = get_message("promise_remind_next_week", user_lang, promise_id=promise_id)
        await query.edit_message_text(text=message, parse_mode='Markdown')
    
    async def _handle_delete_promise(self, query, promise_id: str):
        """Handle delete promise confirmation."""
        keyboard = list(query.message.reply_markup.inline_keyboard)
        confirm_buttons = [
            InlineKeyboardButton(get_message("btn_yes_delete", get_user_language(query.from_user.id)), 
                               callback_data=encode_cb("confirm_delete", pid=promise_id)),
            InlineKeyboardButton(get_message("btn_no_cancel", get_user_language(query.from_user.id)), 
                               callback_data=encode_cb("cancel_delete", pid=promise_id)),
        ]
        keyboard.append(confirm_buttons)
        await query.edit_message_text(
            text=query.message.text_markdown,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    async def _handle_confirm_delete(self, query, promise_id: str, user_lang: Language):
        """Handle confirm delete action."""
        result = self.plan_keeper.delete_promise(query.from_user.id, promise_id)
        await query.edit_message_text(text=result, parse_mode='Markdown')
    
    async def _handle_cancel_delete(self, query):
        """Handle cancel delete action."""
        await query.edit_message_text(
            text=query.message.text_markdown,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(query.message.reply_markup.inline_keyboard[:-1])
        )
    
    async def _handle_report_promise(self, query, promise_id: str, user_lang: Language):
        """Handle promise report generation."""
        report = self.plan_keeper.get_promise_report(query.from_user.id, promise_id)
        await query.edit_message_text(text=report, parse_mode='Markdown')
    
    async def _handle_update_time_spent(self, query, promise_id: str, value: float, current_s: str, user_lang: Language):
        """Handle time spent update."""
        try:
            curr = float(current_s or 0.0)
        except Exception:
            curr = 0.0
        
        delta = float(value)
        if curr <= 0.5:
            new_curr = max(0.0, round_time(curr + delta, step_min=5))
        else:
            new_curr = round_time(curr + delta, step_min=15)
        
        # Get base hours from callback data
        base_h = 0
        try:
            old_cb_data = query.message.reply_markup.inline_keyboard[0][1].callback_data
            old_cb_dict = old_cb_data.split("&")
            old_time = [float(pd[2:]) for pd in old_cb_dict if pd.startswith("v=")]
            base_h = old_time[0] if old_time else 0.0
        except Exception:
            pass
        
        kb = time_options_kb(promise_id, new_curr, base_h)
        await query.edit_message_reply_markup(reply_markup=kb)
        message = get_message("time_selected", user_lang, time=beautify_time(new_curr))
        await query.answer(message)
    
    async def _handle_time_spent(self, query, promise_id: str, value: float, user_lang: Language):
        """Handle time spent selection."""
        if value > 0:
            # Register the action
            self.plan_keeper.add_action(
                user_id=query.from_user.id,
                promise_id=promise_id,
                time_spent=value,
                action_datetime=query.message.date
            )
            message = get_message("time_spent", user_lang, time=beautify_time(value), promise_id=promise_id)
            await query.edit_message_text(text=message, parse_mode='Markdown')
        else:
            # If 0 is selected, consider it a cancellation and delete the message.
            await query.delete_message()
    
    async def _handle_show_more(self, query, context: CallbackContext, cb: dict, user_lang: Language):
        """Handle show more promises."""
        user_id = query.from_user.id
        user_now, _tzname = self._get_user_now(user_id)
        
        # read offset & batch (defaults)
        try:
            offset = int(cb.get("o") or 0)
        except Exception:
            offset = 0
        try:
            batch = int(cb.get("n") or 5)
        except Exception:
            batch = 5
        
        ranked = self.plan_keeper.reminders_service.select_nightly_top(user_id, user_now, n=1000)
        total = len(ranked)
        if offset >= total:
            message = get_message("thats_all", user_lang)
            await query.edit_message_text(message)
            return
        
        # slice the next chunk
        chunk = ranked[offset: offset + batch]
        
        # send items (each with time options)
        for p in chunk:
            weekly_h = float(getattr(p, "hours_per_week", 0.0) or 0.0)
            base_day_h = weekly_h / 7.0
            last = self.plan_keeper.get_last_action_on_promise(user_id, p.id)
            curr_h = float(getattr(last, "time_spent", 0.0) or base_day_h)
            
            kb = time_options_kb(p.id, curr_h=curr_h, base_day_h=base_day_h, weekly_h=weekly_h)
            message = get_message("nightly_question", user_lang, promise_text=p.text.replace('_', ' '))
            await context.bot.send_message(
                chat_id=user_id,
                text=message,
                reply_markup=kb,
                parse_mode="Markdown",
            )
        
        # update the header's button
        new_offset = offset + len(chunk)
        remaining = max(0, total - new_offset)
        if remaining > 0:
            button_text = get_message("show_more_button", user_lang, count=remaining)
            await query.edit_message_reply_markup(
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        button_text,
                        callback_data=encode_cb("show_more", o=new_offset, n=batch)
                    )
                ]])
            )
        else:
            message = get_message("thats_all", user_lang)
            await query.edit_message_text(message)
    
    async def _handle_preping_start(self, query, promise_id: str):
        """Handle preping start action."""
        user_id = query.from_user.id
        sess = self.plan_keeper.sessions_service.start(user_id, promise_id)
        await query.edit_message_text(
            text=self._session_text(sess, elapsed="00:00:00"),
            reply_markup=session_running_kb(sess.session_id),
            parse_mode="Markdown",
        )
        self._schedule_session_ticker(sess)
    
    async def _handle_preping_skip(self, query, promise_id: str, user_lang: Language):
        """Handle preping skip action."""
        user_id = query.from_user.id
        user_now, _tzname = self._get_user_now(user_id)
        
        self.plan_keeper.actions_repo.append_action(
            Action(user_id=user_id, promise_id=promise_id, action="skip", time_spent=0.0, at=user_now)
        )
        message = get_message("session_skipped", user_lang)
        await query.edit_message_text(message)
    
    async def _handle_preping_snooze(self, query, promise_id: str, minutes: int, user_lang: Language):
        """Handle preping snooze action."""
        user_id = query.from_user.id
        user_now, _tzname = self._get_user_now(user_id)
        
        minutes = int(minutes or 30)
        when = user_now + timedelta(minutes=minutes)
        self._schedule_one_pre_ping(user_id, promise_id, when)
        message = get_message("session_snoozed", user_lang, promise_id=promise_id.title(), minutes=minutes)
        await query.edit_message_text(message)
    
    async def _handle_open_time(self, query, promise_id: str):
        """Handle open time options."""
        user_id = query.from_user.id
        promise = self.plan_keeper.get_promise(user_id, promise_id)
        weekly_h = self._hours_per_week_of(promise)
        base_day_h = weekly_h / 7.0
        curr_h = self._last_hours_or(user_id, promise_id, fallback=base_day_h)
        
        kb = time_options_kb(
            promise_id=promise_id,
            curr_h=curr_h,
            base_day_h=base_day_h,
            weekly_h=weekly_h,
            show_timer=True,
        )
        await query.edit_message_reply_markup(reply_markup=kb)
    
    async def _handle_session_pause(self, query, session_id: str):
        """Handle session pause."""
        user_id = query.from_user.id
        sess = self.plan_keeper.sessions_service.pause(user_id, session_id)
        self._stop_ticker(session_id)
        await query.edit_message_reply_markup(reply_markup=session_paused_kb(session_id))
    
    async def _handle_session_resume(self, query, session_id: str):
        """Handle session resume."""
        user_id = query.from_user.id
        sess = self.plan_keeper.sessions_service.resume(user_id, session_id)
        self._schedule_session_ticker(sess)
        await query.edit_message_reply_markup(reply_markup=session_running_kb(session_id))
    
    async def _handle_session_plus(self, query, session_id: str, value: float, user_lang: Language):
        """Handle session time addition."""
        user_id = query.from_user.id
        self.plan_keeper.sessions_service.bump(user_id, session_id, float(value or 0.0))
        message = get_message("time_added", user_lang, time=beautify_time(float(value)))
        await query.answer(message)
    
    async def _handle_session_snooze(self, query, session_id: str, minutes: int, user_lang: Language):
        """Handle session snooze."""
        user_id = query.from_user.id
        user_now, _tzname = self._get_user_now(user_id)
        
        minutes = int(minutes or 10)
        self.plan_keeper.sessions_service.pause(user_id, session_id)
        self._stop_ticker(session_id)
        self._schedule_session_resume(user_id, session_id, user_now + timedelta(minutes=minutes))
        await query.edit_message_reply_markup(reply_markup=session_paused_kb(session_id))
        message = get_message("time_snoozed", user_lang, minutes=minutes)
        await query.answer(message)
    
    async def _handle_session_finish_open(self, query, session_id: str):
        """Handle session finish confirmation."""
        user_id = query.from_user.id
        sess = self.plan_keeper.sessions_service.peek(user_id, session_id)
        proposed_h = self._session_effective_hours(sess)
        await query.edit_message_reply_markup(reply_markup=session_finish_confirm_kb(session_id, proposed_h))
    
    async def _handle_session_finish_confirm(self, query, session_id: str, value: float, user_lang: Language):
        """Handle session finish confirmation."""
        user_id = query.from_user.id
        logged = self.plan_keeper.sessions_service.finish(user_id, session_id, override_hours=float(value))
        self._stop_ticker(session_id)
        message = get_message("session_logged", user_lang, time=beautify_time(float(value)), promise_id=logged.promise_id)
        await query.edit_message_text(message, parse_mode="Markdown")
    
    async def _handle_session_adjust_open(self, query, session_id: str, value: float):
        """Handle session adjust options."""
        await query.edit_message_reply_markup(reply_markup=session_adjust_kb(session_id, base_h=float(value or 0.5)))
    
    async def _handle_session_adjust_set(self, query, session_id: str, value: float, user_lang: Language):
        """Handle session adjust confirmation."""
        user_id = query.from_user.id
        logged = self.plan_keeper.sessions_service.finish(user_id, session_id, override_hours=float(value))
        self._stop_ticker(session_id)
        message = get_message("session_logged", user_lang, time=beautify_time(float(value)), promise_id=logged.promise_id)
        await query.edit_message_text(message)
    
    async def start_pomodoro_timer(self, query, context):
        """Start the Pomodoro timer."""
        user_lang = get_user_language(query.from_user.id)
        total_time = 25  # minutes
        interval = 5  # seconds
        
        for remaining in range(total_time * 60, 0, -interval):
            minutes, seconds = divmod(remaining, 60)
            timer_text = f"Pomodoro Timer: **{minutes:02}:{seconds:02}**"
            try:
                await query.edit_message_text(
                    text=timer_text,
                    parse_mode='Markdown'
                )
                await asyncio.sleep(interval)
            except Exception as e:
                break  # Exit the loop if the message is deleted or another error occurs
        
        finished_message = get_message("pomodoro_finished", user_lang)
        await query.edit_message_text(text=finished_message, parse_mode='Markdown')
        
        break_message = get_message("pomodoro_break", user_lang)
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=break_message,
            parse_mode='Markdown'
        )
    
    async def pre_ping_one(self, context):
        """Job callback: send the pre-ping card."""
        user_id = context.job.data["user_id"]
        promise_id = context.job.data["promise_id"]
        user_lang = get_user_language(user_id)
        
        # resolve promise text
        p = self.plan_keeper.get_promise(user_id, promise_id)
        title = getattr(p, "text", None) or (p.get("text") if isinstance(p, dict) else f"#{promise_id}")
        
        message = get_message("session_ready", user_lang, promise_text=title)
        await context.bot.send_message(
            chat_id=user_id,
            text=message,
            reply_markup=preping_kb(promise_id),
            parse_mode="Markdown",
        )
    
    async def send_nightly_reminders(self, context: CallbackContext, user_id: int = None) -> None:
        """Send nightly reminders to users about their promises."""
        user_id_int = int(user_id)
        user_lang = get_user_language(user_id_int)
        user_now, tzname = self._get_user_now(user_id_int)
        
        # get a bigger ranked list, then slice
        ranked = self.plan_keeper.reminders_service.select_nightly_top(user_id_int, user_now, n=1000)
        if not ranked:
            return
        
        top3, rest = ranked[:3], ranked[3:]
        
        # (optional) header message with "Show more"
        if rest:
            header_message = get_message("nightly_header_with_more", user_lang)
            button_text = get_message("show_more_button", user_lang, count=len(rest))
            await context.bot.send_message(
                chat_id=user_id_int,
                text=header_message,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        button_text,
                        callback_data=encode_cb("show_more", o=3, n=5)
                    )
                ]]),
                parse_mode="Markdown",
            )
        else:
            header_message = get_message("nightly_header", user_lang)
            await context.bot.send_message(
                chat_id=user_id_int,
                text=header_message,
                parse_mode="Markdown",
            )
        
        # send 3 separate messages with time options
        for p in top3:
            weekly_h = float(getattr(p, "hours_per_week", 0.0) or 0.0)
            base_day_h = weekly_h / 7.0
            last = self.plan_keeper.get_last_action_on_promise(user_id_int, p.id)
            curr_h = float(getattr(last, "time_spent", 0.0) or base_day_h)
            
            kb = time_options_kb(p.id, curr_h=curr_h, base_day_h=base_day_h, weekly_h=weekly_h)
            message = get_message("nightly_question", user_lang, promise_text=p.text)
            await context.bot.send_message(
                chat_id=user_id_int,
                text=message,
                reply_markup=kb,
                parse_mode="Markdown",
            )
    
    async def send_morning_reminders(self, context: CallbackContext, user_id: int) -> None:
        """Send morning reminders to users."""
        user_id = int(user_id)
        user_lang = get_user_language(user_id)
        user_now, tzname = self._get_user_now(user_id)
        
        # rank a larger list once, then slice top 3
        ranked = self.plan_keeper.reminders_service.select_nightly_top(user_id, user_now, n=1000)
        if not ranked:
            return
        
        top3 = ranked[:3]
        
        # header (different copy than nightly)
        header_message = get_message("morning_header", user_lang)
        await context.bot.send_message(
            chat_id=user_id,
            text=header_message,
            parse_mode="Markdown",
        )
        
        # per-promise cards with choices
        for p in top3:
            weekly_h = float(getattr(p, "hours_per_week", 0.0) or 0.0)
            base_day_h = weekly_h / 7.0
            
            last = self.plan_keeper.get_last_action_on_promise(user_id, p.id)
            curr_h = float(getattr(last, "time_spent", 0.0) or base_day_h)
            
            message = get_message("morning_question", user_lang, promise_text=p.text)
            await context.bot.send_message(
                chat_id=user_id,
                text=message,
                reply_markup=preping_kb(p.id, snooze_min=30),
                parse_mode="Markdown",
            )
