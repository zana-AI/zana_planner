"""
Callback handlers for the Telegram bot.
Handles all callback query processing from inline keyboards.
"""

import asyncio
import io
import os
from datetime import datetime, timedelta
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import CallbackContext

from handlers.messages_store import get_message, get_user_language, Language
from services.planner_api_adapter import PlannerAPIAdapter
from services.response_service import ResponseService
from platforms.interfaces import IResponseService
from models.models import Action
from utils.time_utils import beautify_time, round_time, get_week_range
from ui.keyboards import (
    time_options_kb, session_running_kb, session_paused_kb, 
    session_finish_confirm_kb, session_adjust_kb, preping_kb,
    language_selection_kb, weekly_report_kb, morning_calendar_kb,
    mini_app_kb
)
from ui.messages import weekly_report_text
from cbdata import encode_cb, decode_cb
from utils.bot_utils import BotUtils
from utils.logger import get_logger

logger = get_logger(__name__)


def _is_staging_or_test_mode() -> bool:
    env = (os.getenv("ENV", "") or os.getenv("ENVIRONMENT", "")).lower()
    if env in {"staging", "stage", "test", "testing"}:
        return True
    return os.getenv("PYTEST_CURRENT_TEST") is not None


class CallbackHandlers:
    """Handles all callback query processing."""
    
    def __init__(self, plan_keeper: PlannerAPIAdapter, application, response_service: IResponseService, miniapp_url: str = "https://xaana.club"):
        self.plan_keeper = plan_keeper
        self.application = application
        self.response_service = response_service
        self.miniapp_url = miniapp_url
    
    def get_user_timezone(self, user_id: int) -> str:
        """Get user timezone using the settings service."""
        return self.plan_keeper.settings_service.get_user_timezone(user_id)
    
    def _update_user_info(self, user_id: int, user) -> None:
        """Extract and update user info (first_name, username, last_seen) from Telegram user object."""
        try:
            settings = self.plan_keeper.settings_service.get_settings(user_id)
            updated = False
            
            # Only set first_name from Telegram if not already stored
            # (preserves any name the user set manually in settings)
            if user.first_name and not settings.first_name:
                settings.first_name = user.first_name
                updated = True
            
            # Update username if missing or changed
            if user.username:
                if settings.username != user.username:
                    settings.username = user.username
                    updated = True
            
            # Always update last_seen
            settings.last_seen = datetime.now()
            updated = True
            
            if updated:
                self.plan_keeper.settings_service.save_settings(settings)
        except Exception as e:
            logger.warning(f"Failed to update user info for user {user_id}: {e}")
    
    def _get_user_now(self, user_id: int):
        """Return (now_in_user_tz, tzname)."""
        return BotUtils.get_user_now(self.plan_keeper, user_id)
    
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

    async def cleanup_unread_morning_messages(self, context: CallbackContext, user_id: int) -> None:
        """Clean up morning reminder messages that haven't been interacted with."""
        try:
            if 'morning_messages' not in self.application.bot_data:
                return
                
            user_messages = self.application.bot_data['morning_messages'].get(user_id, [])
            message_ids = [msg_info['message_id'] for msg_info in user_messages]
            for msg_id in message_ids:
                try:
                    # Try to delete the message
                    # If it was edited (user interacted), this will fail
                    await context.bot.delete_message(
                        chat_id=user_id,
                        message_id=msg_id,
                    )
                    logger.info(f"Deleted unread morning message {msg_id} for user {user_id}")
                except Exception as e:
                    # Message was likely edited (user interacted) or already deleted
                    logger.debug(f"Could not delete message {msg_id}: {str(e)}")
            
            # Clear stored message IDs for this user
            if user_id in self.application.bot_data['morning_messages']:
                del self.application.bot_data['morning_messages'][user_id]
                
        except Exception as e:
            logger.error(f"Error during noon cleanup for user {user_id}: {str(e)}")
    
    def _schedule_session_ticker(self, sess):
        """Schedule session ticker."""
        # TODO: implement session ticker functionality
        return
    
    def _stop_ticker(self, session_id: str):
        """Stop session ticker."""
        # TODO: implement stop ticker functionality
        return
    
    def _schedule_session_resume(self, user_id: int, session_id: str, when_dt: datetime):
        """Schedule session resume."""
        # TODO: implement session resume scheduling functionality
        return
    
    def _session_text(self, sess, elapsed: str) -> str:
        """Generate session text."""
        return (f"⏱ *Session for #{sess.promise_id}: {self.plan_keeper.promises_repo.get_promise(sess.user_id, sess.promise_id).text}*"
                f"\nStarted {sess.started_at.strftime('%H:%M')} | Elapsed: {elapsed}")
    
    def _session_effective_hours(self, sess) -> float:
        """Calculate effective hours for session."""
        # TODO: implement proper session effective hours calculation
        return 0.5  # placeholder

    def _sync_llm_external_turn(
        self,
        user_id: int,
        user_text: str,
        bot_text: str,
        *,
        drop_pending_confirmation_tail: bool = False,
    ) -> None:
        """Sync non-LLM callback interactions into LLM in-memory history."""
        try:
            llm_handler = (self.application.bot_data or {}).get("llm_handler") if self.application else None
            if llm_handler and hasattr(llm_handler, "record_external_turn"):
                llm_handler.record_external_turn(
                    str(user_id),
                    user_text,
                    bot_text,
                    drop_pending_confirmation_tail=drop_pending_confirmation_tail,
                )
        except Exception as e:
            logger.debug("Could not sync external callback turn for user %s: %s", user_id, e)
    
    async def handle_promise_callback(self, update: Update, context: CallbackContext) -> None:
        """Handle all callback queries from inline keyboards."""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        user_lang = get_user_language(query.from_user)
        # User info updated in PlannerBot.dispatch()

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
        elif action == "mut_confirm":
            await self._handle_mutation_confirmation(query, context, cb, user_lang)
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
        elif action == "session_abort":
            await self._handle_session_abort(query, session_id, user_lang)
        elif action == "refresh_weekly":
            await self._handle_refresh_weekly(query, context, user_lang)
        elif action == "set_language":
            await self._handle_set_language(query)
        elif action == "tz_confirm":
            # Get timezone from callback data
            tz = cb.get("tz")
            await self._handle_timezone_confirm(query, tz, user_lang)
        elif action == "tz_not_now":
            await self._handle_timezone_dismiss(query, user_lang)
        elif action == "tz_choose":
            await self._handle_timezone_choose(query, user_lang)
        elif action == "voice_mode":
            await self._handle_voice_mode(query, cb, user_lang)
        elif action == "plan_morning_session":
            idx = int(cb.get("idx", 0))
            await self._handle_plan_morning_session(query, idx, user_lang)
        elif action == "noop":
            await query.answer()
        elif action == "add_to_calendar_yes":
            await self._handle_add_to_calendar_yes(query, context, user_lang)
        elif action == "add_to_calendar_no":
            await self._handle_add_to_calendar_no(query, user_lang)
        elif action == "summarize_content":
            url_id = cb.get("url_id")
            # Retrieve URL from bot_data storage
            url = None
            if url_id and 'content_urls' in self.application.bot_data:
                url = self.application.bot_data['content_urls'].get(url_id)
            
            if not url:
                await query.answer("Error: URL not found. Please try sharing the link again.", show_alert=True)
                return
            
            await self._handle_summarize_content(query, url, user_id, user_lang)
        elif action == "youtube_transcript":
            url_id = cb.get("url_id")
            video_id = cb.get("vid")
            url = None
            if url_id and "content_urls" in self.application.bot_data:
                url = self.application.bot_data["content_urls"].get(url_id)
            if not url:
                await query.answer("Error: URL not found. Please try sharing the link again.", show_alert=True)
                return
            await self._handle_youtube_transcript(query, context, url, user_id, video_id, user_lang)
        elif action == "add_content":
            await self._handle_add_content(query, user_id, cb.get("cid"), cb.get("url_id"), user_lang)
        elif action == "broadcast_schedule":
            await self._handle_broadcast_schedule(query, context, user_lang)
        elif action == "broadcast_cancel":
            await self._handle_broadcast_cancel(query, context, user_lang)
        elif action == "suggest_accept":
            suggestion_id = cb.get("sid")
            await self._handle_suggestion_accept(query, suggestion_id, user_lang)
        elif action == "suggest_decline":
            suggestion_id = cb.get("sid")
            await self._handle_suggestion_decline(query, suggestion_id, user_lang)
        else:
            logger.warning(f"Unknown callback action: {action}")
    
    async def _handle_pomodoro_start(self, query, context):
        """Handle pomodoro timer start."""
        await self.start_pomodoro_timer(query, context)
    
    async def _handle_pomodoro_pause(self, query, user_lang: Language):
        """Handle pomodoro timer pause."""
        message = get_message("pomodoro_paused", user_lang)
        user_id = query.from_user.id if query.from_user else None
        await self.response_service.edit_message_text(
            query, message,
            user_id=user_id,
            parse_mode='Markdown'
        )
    
    async def _handle_pomodoro_stop(self, query, user_lang: Language):
        """Handle pomodoro timer stop."""
        message = get_message("pomodoro_stopped", user_lang)
        user_id = query.from_user.id if query.from_user else None
        await self.response_service.edit_message_text(
            query, message,
            user_id=user_id,
            parse_mode='Markdown'
        )
    
    async def _handle_remind_next_week(self, query, promise_id: str, user_lang: Language):
        """Handle remind next week action."""
        next_monday = (datetime.now() + timedelta(days=(7 - datetime.now().weekday()))).date()
        self.plan_keeper.update_promise_start_date(query.from_user.id, promise_id, next_monday)
        message = get_message("promise_remind_next_week", user_lang, promise_id=promise_id)
        user_id = query.from_user.id if query.from_user else None
        await self.response_service.edit_message_text(
            query, message,
            user_id=user_id,
            parse_mode='Markdown'
        )
    
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
        user_id = query.from_user.id if query.from_user else None
        await self.response_service.edit_message_text(
            query, query.message.text_markdown,
            user_id=user_id,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(query.message.reply_markup.inline_keyboard[:-1])
        )

    async def _handle_mutation_confirmation(self, query, context: CallbackContext, cb: dict, user_lang: Language):
        """Handle Yes/Skip confirmation buttons for pending mutation actions."""
        user_id = query.from_user.id
        decision = str((cb or {}).get("d", "")).strip().lower()
        is_confirm = decision in {"yes", "confirm", "y", "1", "true"}

        pending = (context.user_data or {}).get("pending_clarification") if hasattr(context, "user_data") else None
        if not pending or str(pending.get("reason", "")).strip().lower() != "pre_mutation_confirmation":
            msg = get_message("confirmation_expired", user_lang)
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            try:
                await query.message.reply_text(msg)
            except Exception:
                logger.debug("Could not send expired confirmation message to user %s", user_id)
            return

        tool_name = str(pending.get("tool_name", "")).strip()
        tool_args = pending.get("tool_args") or {}
        batch_remaining = list(pending.get("batch_remaining") or [])
        batch_total = int(pending.get("batch_total") or 1)
        batch_current_idx = int(pending.get("batch_current_idx") or 0)
        step_label = pending.get("description") or tool_name

        # Clear pending confirmation before executing
        try:
            context.user_data.pop("pending_clarification", None)
        except Exception:
            pass

        # --- Execute or skip the current item ---
        _step_ok = True  # set to False only on unexpected tool error
        if is_confirm:
            try:
                if hasattr(self.plan_keeper, tool_name):
                    method = getattr(self.plan_keeper, tool_name)
                    tool_args_with_user = {**tool_args, "user_id": user_id}
                    method(**tool_args_with_user)

                    if tool_name in ("add_promise", "create_promise"):
                        promise_text = tool_args.get("promise_text") or tool_args.get("text", "promise")
                        step_result = get_message(
                            "promise_created_confirmed",
                            user_lang,
                            promise_text=str(promise_text).replace("_", " "),
                        )
                    elif tool_name == "subscribe_template":
                        template_id = tool_args.get("template_id", "template")
                        step_result = get_message("template_subscribed_confirmed", user_lang, template_id=template_id)
                    else:
                        step_result = get_message("action_confirmed", user_lang)
                else:
                    step_result = get_message("error_tool_not_found", user_lang, tool_name=tool_name)
            except Exception as e:
                logger.error("Error executing confirmed tool %s for user %s: %s", tool_name, user_id, e)
                step_result = get_message("error_executing_action", user_lang, error=str(e))
                _step_ok = False
        else:
            # Skip this item — note it for the progress line, then continue
            step_result = f"⏭ Skipped: {step_label}."

        _progress_icon = "✅" if _step_ok else "❌"

        # --- Continue batch or finalise ---
        if batch_remaining:
            next_item = batch_remaining[0]
            remaining_after = batch_remaining[1:]
            next_idx = batch_current_idx + 1
            next_desc = next_item.get("description", next_item.get("tool_name", "next action"))
            done_so_far = next_idx  # items processed including the current one

            if not remaining_after:
                next_q = (
                    f"{_progress_icon} ({done_so_far}/{batch_total}) {step_result}\n\n"
                    f"Last one — {next_desc}. Proceed?"
                )
            else:
                next_q = (
                    f"{_progress_icon} ({done_so_far}/{batch_total}) {step_result}\n\n"
                    f"Next ({done_so_far + 1}/{batch_total}): {next_desc}. Continue?"
                )

            new_pending = {
                "reason": "pre_mutation_confirmation",
                "tool_name": next_item["tool_name"],
                "tool_args": next_item["tool_args"],
                "description": next_desc,
                "batch_remaining": remaining_after,
                "batch_total": batch_total,
                "batch_current_idx": next_idx,
            }
            try:
                context.user_data["pending_clarification"] = new_pending
            except Exception:
                pass

            yes_text = get_message("btn_yes_confirm", user_lang)
            skip_text = get_message("btn_skip_action", user_lang)
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(yes_text, callback_data=encode_cb("mut_confirm", d="yes")),
                InlineKeyboardButton(skip_text, callback_data=encode_cb("mut_confirm", d="skip")),
            ]])
            try:
                await query.edit_message_text(next_q, reply_markup=kb)
            except Exception:
                await query.message.reply_text(next_q, reply_markup=kb)
            return

        # No more items — show final result and sync history
        try:
            await query.edit_message_text(step_result)
        except Exception:
            await query.message.reply_text(step_result)
        self._sync_llm_external_turn(
            user_id,
            "yes",
            step_result,
            drop_pending_confirmation_tail=True,
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
        await self.response_service.edit_message_reply_markup(query, reply_markup=kb)
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
            promise = self.plan_keeper.get_promise(query.from_user.id, promise_id)
            promise_text = (promise.text.replace('_', ' ') if promise else f"#{promise_id}")
            message = get_message("time_spent", user_lang, time=beautify_time(value),
                                  date=query.message.date.strftime("%A"),
                                  promise_id=promise_id, promise_text=promise_text.replace("_", " "))
            try:
                user_id = query.from_user.id if query.from_user else None
                await self.response_service.edit_message_text(
                    query, message,
                    user_id=user_id,
                    parse_mode='Markdown'
                )
            except Exception:
                user_id = query.from_user.id if query.from_user else None
                await self.response_service.edit_message_text(
                    query, message,
                    user_id=user_id
                )
        else:
            # If 0 is selected, consider it a cancellation and delete the message.
            await query.delete_message()
    
    async def _handle_show_more(self, query, context: CallbackContext, cb: dict, user_lang: Language):
        """Handle show more promises."""
        user_id = query.from_user.id
        user_now, _tzname = self._get_user_now(user_id)
        current_date = user_now.date()
        
        # Reset state if it's a new day
        self.plan_keeper.nightly_state_repo.reset_for_new_day(user_id, current_date)
        
        # Get already shown promise IDs for today
        shown_promise_ids = self.plan_keeper.nightly_state_repo.get_shown_promise_ids(user_id, current_date)
        
        # read batch size (defaults)
        try:
            batch = int(cb.get("n") or 5)
        except Exception:
            batch = 5
        
        # Get ranked list and filter out already shown promises
        ranked = self.plan_keeper.reminders_service.select_nightly_top(user_id, user_now, n=1000)
        unshown_ranked = [p for p in ranked if p.id not in shown_promise_ids]
        
        if not unshown_ranked:
            # All promises have been shown today
            message = get_message("thats_all", user_lang)
            user_id = query.from_user.id if query.from_user else None
            await self.response_service.edit_message_text(
                query, message,
                user_id=user_id
            )
            return
        
        # slice the next chunk (show next batch_size items)
        chunk = unshown_ranked[:batch]
        
        # send items (each with time options)
        shown_ids = []
        for p in chunk:
            weekly_h = float(getattr(p, "hours_per_week", 0.0) or 0.0)
            base_day_h = weekly_h / 7.0
            last = self.plan_keeper.get_last_action_on_promise(user_id, p.id)
            curr_h = float(getattr(last, "time_spent", 0.0) or base_day_h)
            
            kb = time_options_kb(p.id, curr_h=curr_h, base_day_h=base_day_h, weekly_h=weekly_h)
            message = get_message("nightly_question", user_lang, promise_text=p.text.replace('_', ' '))
            # Use ResponseService for send_message
            await self.response_service.send_message(
                context,
                chat_id=user_id,
                text=message,
                user_id=user_id,
                reply_markup=kb,
                parse_mode="Markdown",
            )
            shown_ids.append(p.id)
        
        # Mark these promises as shown
        if shown_ids:
            self.plan_keeper.nightly_state_repo.mark_promises_as_shown(user_id, shown_ids, current_date)
        
        # update the header's button
        remaining = unshown_ranked[len(chunk):]
        if remaining:
            button_text = get_message("show_more_button", user_lang, count=len(remaining))
            await query.edit_message_reply_markup(
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        button_text,
                        callback_data=encode_cb("show_more", n=batch)
                    )
                ]])
            )
        else:
            message = get_message("thats_all", user_lang)
            user_id = query.from_user.id if query.from_user else None
            await self.response_service.edit_message_text(
                query, message,
                user_id=user_id
            )
    
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
            # TODO: show_timer parameter not implemented in time_options_kb function
        )
        await self.response_service.edit_message_reply_markup(query, reply_markup=kb)
    
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
    
    async def _handle_session_abort(self, query, session_id: str, user_lang: Language):
        """Handle session abort (discard without logging)."""
        user_id = query.from_user.id
        aborted = self.plan_keeper.sessions_service.abort(user_id, session_id)
        self._stop_ticker(session_id)
        if aborted:
            # Try to get a translated message, fallback to English
            try:
                message = get_message("session_discarded", user_lang)
            except:
                message = "❌ Session discarded — not logged."
            await query.edit_message_text(message, parse_mode="Markdown")
        else:
            await query.answer("Session not found or already finished.", show_alert=True)
    
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
        promise_text = getattr(p, "text", None) or (p.get("text") if isinstance(p, dict) else f"#{promise_id}")
        
        message = get_message("session_ready", user_lang, promise_text=promise_text.replace('_', ' '))
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
        current_date = user_now.date()
        is_quiet_mode = _is_staging_or_test_mode()
        
        if is_quiet_mode:
            logger.debug(f"[REMINDER] send_nightly_reminders: user_id={user_id_int}, now={user_now}, tz={tzname}, date={current_date}")
        else:
            logger.info(f"[REMINDER] send_nightly_reminders: user_id={user_id_int}, now={user_now}, tz={tzname}, date={current_date}")
        
        # Check if user has any promises
        ranked = self.plan_keeper.reminders_service.select_nightly_top(user_id_int, user_now, n=1000)
        if is_quiet_mode:
            logger.debug(f"[REMINDER] Found {len(ranked)} ranked promises for user {user_id_int}")
        else:
            logger.info(f"[REMINDER] Found {len(ranked)} ranked promises for user {user_id_int}")
        if not ranked:
            if is_quiet_mode:
                logger.debug(f"[REMINDER] No promises found for user {user_id_int} - skipping reminder")
            else:
                logger.warning(f"[REMINDER] No promises found for user {user_id_int} - skipping reminder")
            return
        
        # Send single wrap-up message with mini app button
        prompt = get_message("nightly_wrapup_prompt", user_lang)
        button_text = get_message("btn_open_app", user_lang)
        url = f"{self.miniapp_url}/dashboard"
        
        await context.bot.send_message(
            chat_id=user_id_int,
            text=prompt,
            reply_markup=mini_app_kb(url, button_text=button_text),
            parse_mode="Markdown",
        )
        if is_quiet_mode:
            logger.debug(f"[REMINDER] Sent nightly wrap-up message with mini app button for user {user_id_int}")
        else:
            logger.info(f"[REMINDER] Sent nightly wrap-up message with mini app button for user {user_id_int}")
    
    async def send_morning_reminders(self, context: CallbackContext, user_id: int) -> None:
        """Send morning reminders to users."""
        user_id = int(user_id)
        # Get user language from settings
        from handlers.messages_store import _translation_manager
        if _translation_manager:
            user_lang = _translation_manager.get_user_language(user_id)
        else:
            user_lang = Language.EN
        user_now, tzname = self._get_user_now(user_id)
        
        # Check if user has promises
        promises = self.plan_keeper.get_promises(user_id)
        if not promises:
            return
        
        # rank a larger list once, then slice top 3
        ranked = self.plan_keeper.reminders_service.select_nightly_top(user_id, user_now, n=1000)
        if not ranked:
            return
        
        top3 = ranked[:3]
        
        # Store top 3 promises in bot_data for calendar callback handler
        if 'morning_top3' not in self.application.bot_data:
            self.application.bot_data['morning_top3'] = {}
        self.application.bot_data['morning_top3'][user_id] = [
            {
                'id': p.id,
                'text': p.text.replace('_', ' '),
                'weekly_h': getattr(p, 'hours_per_week', 0.0) or 0.0,
            }
            for p in top3
        ]
        
        # Get work hour suggestion
        day_of_week = user_now.strftime("%A")
        work_suggestion = None
        try:
            # Get LLM handler if available
            llm_handler = self.application.bot_data.get('llm_handler')
            if llm_handler:
                self.plan_keeper.set_llm_handler(llm_handler)
            
            work_suggestion = self.plan_keeper.get_work_hour_suggestion(user_id, day_of_week)
        except Exception as e:
            logger.warning(f"Error getting work hour suggestion: {str(e)}")
        
        # Pre-compute session proposals: per-task duration + LLM-suggested start times
        today_str = user_now.strftime("%Y-%m-%d")

        def _nice_dur(weekly_h: float) -> int:
            raw_min = (weekly_h / 5) * 60 if weekly_h > 0 else 60
            steps = [20, 25, 30, 45, 60, 75, 90, 120, 150, 180, 240]
            return min(steps, key=lambda s: abs(s - raw_min))

        day_proposals = []
        try:
            _llm = self.application.bot_data.get('llm_handler')
            tasks_meta = [
                {
                    'promise_id': p.id,
                    'text': p.text.replace('_', ' '),
                    'duration_min': _nice_dur(getattr(p, 'hours_per_week', 0.0) or 0.0),
                }
                for p in top3
            ]
            start_times: list = [None] * len(tasks_meta)
            if _llm:
                import json as _json, re as _re
                tasks_lines_str = "\n".join(
                    f"{i + 1}. {t['text']} — {t['duration_min']} min"
                    for i, t in enumerate(tasks_meta)
                )
                sched_prompt = (
                    f"Schedule sessions for {day_of_week} {today_str} timezone {tzname}. "
                    f"Current time: {user_now.strftime('%H:%M')}.\n"
                    f"Tasks:\n{tasks_lines_str}\n"
                    f"Rules: start ≥ 08:30, ≥15 min gap, deep work first, round times.\n"
                    f'Return ONLY JSON: [{{"task_index": 0, "start_time": "HH:MM"}}, ...]'
                )
                raw = _llm.get_response_custom(sched_prompt, str(user_id))
                m = _re.search(r'\[.*?\]', raw, _re.DOTALL)
                if m:
                    for entry in _json.loads(m.group()):
                        k = entry.get('task_index')
                        if k is not None and 0 <= k < len(start_times):
                            start_times[k] = entry.get('start_time')
            fallbacks = ["09:00", "11:00", "14:00"]
            for i, st in enumerate(start_times):
                if not st:
                    start_times[i] = fallbacks[i] if i < len(fallbacks) else "09:00"
            day_proposals = [
                {
                    'promise_id': t['promise_id'],
                    'text': t['text'],
                    'duration_min': t['duration_min'],
                    'planned_start': f"{today_str}T{start_times[i]}:00",
                }
                for i, t in enumerate(tasks_meta)
            ]
        except Exception as e:
            logger.warning(f"Error computing session proposals for user {user_id}: {e}")
            day_proposals = [
                {
                    'promise_id': p.id,
                    'text': p.text.replace('_', ' '),
                    'duration_min': _nice_dur(getattr(p, 'hours_per_week', 0.0) or 0.0),
                    'planned_start': None,
                }
                for p in top3
            ]

        if 'morning_sessions_proposed' not in self.application.bot_data:
            self.application.bot_data['morning_sessions_proposed'] = {}
        self.application.bot_data['morning_sessions_proposed'][user_id] = day_proposals

        # Build priorities list with emojis
        emojis = ['1️⃣', '2️⃣', '3️⃣']
        priorities_text = get_message("morning_priorities_header", user_lang, count=len(top3)) + "\n\n"
        for i, p in enumerate(top3):
            promise_text = p.text.replace('_', ' ')
            priorities_text += f"{emojis[i]} {promise_text}\n"

        # Add work hour suggestion if available
        suggestion_text = ""
        if work_suggestion and work_suggestion.get('suggested_hours', 0) > 0:
            suggested_hours = work_suggestion['suggested_hours']
            suggestion_text = "\n\n" + get_message("work_hours_suggestion", user_lang,
                                                   hours=suggested_hours, day=day_of_week)

        # Build full message
        header_message = get_message("morning_header", user_lang, date=user_now.strftime("%A"))
        calendar_question = get_message("morning_calendar_question", user_lang)
        full_message = f"{header_message}\n\n{priorities_text}{suggestion_text}\n\n{calendar_question}"

        # Send message with one button per task
        msg = await context.bot.send_message(
            chat_id=user_id,
            text=full_message,
            reply_markup=morning_calendar_kb(tasks=day_proposals),
            parse_mode="Markdown",
        )

        # Store message ID for cleanup
        self._store_morning_message_id(user_id, msg.message_id, "morning_priorities")

    def _store_morning_message_id(self, user_id: int, message_id: int, promise_id: str) -> None:
        """Store morning message ID for later cleanup."""
        # Store in a simple file or database
        # For now, we'll use a simple approach with bot_data
        if 'morning_messages' not in self.application.bot_data:
            self.application.bot_data['morning_messages'] = {}
        
        if user_id not in self.application.bot_data['morning_messages']:
            self.application.bot_data['morning_messages'][user_id] = []
        
        self.application.bot_data['morning_messages'][user_id].append({
            'message_id': message_id,
            'promise_id': promise_id,
            'sent_at': datetime.now()
        })

    async def _handle_refresh_weekly(self, query, context: CallbackContext, user_lang: Language):
        """Handle weekly report refresh - re-generates the report card as a single photo message with caption."""
        user_id = query.from_user.id
        
        # Get current time in user's timezone
        user_now, _tzname = self._get_user_now(user_id)
        
        # Get fresh weekly summary
        summary = self.plan_keeper.reports_service.get_weekly_summary(user_id, user_now)
        report = weekly_report_text(summary)
        
        # Compute week boundaries based on current time
        week_start, week_end = get_week_range(user_now)
        # week_end is next Monday, so for display we want Sunday (6 days after Monday)
        week_end_display = week_start + timedelta(days=6)
        date_range_str = f"{week_start.strftime('%d %b')} - {week_end_display.strftime('%d %b')}"
        
        # Create keyboard with refresh and mini app buttons
        keyboard = weekly_report_kb(user_now, self.miniapp_url)
        
        # Build message text
        header = get_message("weekly_header", user_lang, date_range=date_range_str)
        message_text = f"{header}\n\n{report}"

        # Telegram message text limit handling
        MAX_MESSAGE_LEN = 4096
        if len(message_text) > MAX_MESSAGE_LEN:
            message_text = message_text[: MAX_MESSAGE_LEN - 1] + "…"
        
        # Image generation disabled - send text-only weekly report with mini app button
        # Note: Re-enable image generation if needed in the future
        # image_path = await self.plan_keeper.reports_service.generate_weekly_visualization_image(
        #     user_id, user_now
        # )
        
        try:
            # Answer the callback query first
            await query.answer("Refreshing weekly report...")
            
            # Send text message with keyboard
            await context.bot.send_message(
                chat_id=user_id,
                text=message_text,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            
            # Try to delete the old message (if it exists and is deletable)
            try:
                await query.message.delete()
            except Exception as e:
                logger.debug(f"Could not delete old message: {e}")
                # It's okay if we can't delete it - the new message is already sent
        except Exception as e:
            logger.error(f"Error refreshing weekly report: {e}")
            await query.answer("Error refreshing report. Please try again.")
    
    async def _handle_set_language(self, query):
        """Handle language selection."""
        user_id = query.from_user.id
        try:
            selected_lang = query.data.split("&")[1].split("=")[1].strip("")
        except Exception:
            selected_lang = query.from_user.language_code
        
        # Save language to settings
        settings = self.plan_keeper.settings_service.get_settings(user_id)
        settings.language = selected_lang
        self.plan_keeper.settings_service.save_settings(settings)
        
        # Clear language cache since language changed
        if hasattr(self, 'response_service') and self.response_service:
            self.response_service.clear_lang_cache(user_id)
        
        # Send confirmation message in selected language
        confirmation_message = get_message("language_set", selected_lang, lang=selected_lang)
        await query.edit_message_text(text=confirmation_message, parse_mode='Markdown')
        
        # Check if this is a new user (no promises) and show welcome message
        promises = self.plan_keeper.get_promises(user_id)
        if len(promises) == 0:
            # This is a new user, show welcome message
            welcome_message = get_message("welcome_new", selected_lang)
            await query.message.reply_text(welcome_message, parse_mode='Markdown')
    
    async def _handle_timezone_confirm(self, query, tz: str, user_lang: Language):
        """Handle timezone confirmation - user wants to use detected timezone."""
        user_id = query.from_user.id
        
        # Cancel any pending delayed messages for this user (they're active now)
        try:
            from services.delayed_message_service import get_delayed_message_service
            delayed_service = get_delayed_message_service()
            if delayed_service:
                delayed_service.cancel_pending(user_id)
        except Exception as e:
            logger.debug(f"Could not cancel pending messages: {e}")
        
        # Update timezone
        if tz:
            self.plan_keeper.settings_service.set_user_timezone(user_id, tz)
            
            # Send confirmation message
            from handlers.messages_store import get_message
            confirm_msg = get_message("timezone_updated", user_lang, timezone=tz)
            await query.edit_message_text(confirm_msg)
            logger.info(f"User {user_id} confirmed timezone update to {tz}")
        else:
            await query.answer("Error: Timezone not specified.", show_alert=True)
    
    async def _handle_timezone_dismiss(self, query, user_lang: Language):
        """Handle timezone dismiss - user doesn't want to set timezone now."""
        user_id = query.from_user.id
        
        # Cancel any pending delayed messages for this user (they're active now)
        try:
            from services.delayed_message_service import get_delayed_message_service
            delayed_service = get_delayed_message_service()
            if delayed_service:
                delayed_service.cancel_pending(user_id)
        except Exception as e:
            logger.debug(f"Could not cancel pending messages: {e}")
        
        # Send dismiss message
        from handlers.messages_store import get_message
        dismiss_msg = get_message("timezone_dismissed", user_lang)
        await query.edit_message_text(dismiss_msg)
        logger.info(f"User {user_id} dismissed timezone update")
    
    async def _handle_timezone_choose(self, query, user_lang: Language):
        """Handle timezone choose - user wants to select different timezone."""
        user_id = query.from_user.id
        
        # Cancel any pending delayed messages for this user (they're active now)
        try:
            from services.delayed_message_service import get_delayed_message_service
            delayed_service = get_delayed_message_service()
            if delayed_service:
                delayed_service.cancel_pending(user_id)
        except Exception as e:
            logger.debug(f"Could not cancel pending messages: {e}")
        
        # Send message with button to open timezone selector in Mini App
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
        from handlers.messages_store import get_message
        
        timezone_url = f"{self.miniapp_url}/timezone"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Open Timezone Selector", web_app=WebAppInfo(url=timezone_url))]
        ])
        
        msg = "Please select your timezone in the app that will open."
        await query.edit_message_text(msg, reply_markup=keyboard)
        logger.info(f"User {user_id} chose to select timezone manually")
    
    async def _handle_voice_mode(self, query, cb, user_lang):
        """Handle voice mode preference selection."""
        user_id = query.from_user.id
        enabled_str = cb.get("enabled", "false")
        enabled = enabled_str.lower() == "true"
        
        # Save voice mode preference
        settings = self.plan_keeper.settings_service.get_settings(user_id)
        settings.voice_mode = "enabled" if enabled else "disabled"
        self.plan_keeper.settings_service.save_settings(settings)
        
        # Send confirmation message
        if enabled:
            confirmation_message = get_message("voice_mode_enabled", user_lang)
        else:
            confirmation_message = get_message("voice_mode_disabled", user_lang)
        
        await query.edit_message_text(text=confirmation_message, parse_mode='Markdown')
    
    async def _handle_add_to_calendar_yes(self, query, context: CallbackContext, user_lang: Language):
        """Create planned sessions for today's top-3 priorities."""
        user_id = query.from_user.id
        user_now, tzname = self._get_user_now(user_id)

        top3_promises = self.application.bot_data.get('morning_top3', {}).get(user_id, [])
        if not top3_promises:
            await query.answer("Sorry, I couldn't find your priorities. Please try again tomorrow.")
            return

        await query.answer("Planning your sessions... ⏳")

        # Round weekly_h/5 to a natural session length (minutes)
        def _nice_duration(weekly_h: float) -> int:
            raw_min = (weekly_h / 5) * 60 if weekly_h > 0 else 60
            steps = [20, 25, 30, 45, 60, 75, 90, 120, 150, 180, 240]
            return min(steps, key=lambda s: abs(s - raw_min))

        tasks_for_prompt = [
            {
                'index': i,
                'text': p['text'],
                'duration_min': _nice_duration(p.get('weekly_h', 0.0)),
            }
            for i, p in enumerate(top3_promises)
        ]

        tasks_lines = "\n".join(
            f"{i + 1}. {t['text']} — {t['duration_min']} min"
            for i, t in enumerate(tasks_for_prompt)
        )
        current_time_str = user_now.strftime("%H:%M")
        today_str = user_now.strftime("%Y-%m-%d")
        day_name = user_now.strftime("%A")

        prompt = f"""You are a productivity assistant scheduling work sessions for a user.

Today is {day_name} {today_str} in timezone {tzname}. Current time: {current_time_str}.

Tasks to schedule today with their suggested durations:
{tasks_lines}

Rules:
- Schedule sessions after {current_time_str}, starting no earlier than 08:30
- Leave at least 15 minutes between sessions
- Deep-work tasks should come first (peak focus in the morning)
- Use natural round times (e.g. 09:00, 09:30, 10:00)

Return ONLY a valid JSON array with this exact shape, no extra text:
[
  {{"task_index": 0, "start_time": "HH:MM"}},
  {{"task_index": 1, "start_time": "HH:MM"}},
  {{"task_index": 2, "start_time": "HH:MM"}}
]"""

        start_times: list = [None] * len(tasks_for_prompt)
        try:
            llm_handler = self.application.bot_data.get('llm_handler')
            if llm_handler:
                import json, re as _re
                raw = llm_handler.get_response_custom(prompt, str(user_id))
                # Extract JSON array from response
                json_match = _re.search(r'\[.*?\]', raw, _re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group())
                    for entry in parsed:
                        idx = entry.get('task_index')
                        if idx is not None and 0 <= idx < len(start_times):
                            start_times[idx] = entry.get('start_time')
        except Exception as e:
            logger.warning(f"LLM session time suggestion failed for user {user_id}: {e}")

        # Fallback times if LLM parsing fails
        fallbacks = ["09:00", "11:00", "14:00", "16:00"]
        for i, t in enumerate(start_times):
            if not t:
                start_times[i] = fallbacks[i] if i < len(fallbacks) else "09:00"

        # Create plan sessions and build confirmation
        emojis = ['1️⃣', '2️⃣', '3️⃣']
        lines = []
        for i, task in enumerate(tasks_for_prompt):
            start_iso = f"{today_str}T{start_times[i]}:00"
            try:
                self.plan_keeper.add_plan_session(
                    user_id=user_id,
                    promise_id=top3_promises[i]['id'],
                    title=task['text'],
                    planned_start=start_iso,
                    planned_duration_min=task['duration_min'],
                )
                lines.append(f"{emojis[i]} {task['text']} — {start_times[i]}, {task['duration_min']} min")
            except Exception as e:
                logger.error(f"Failed to create plan session for promise {top3_promises[i]['id']}: {e}")
                lines.append(f"{emojis[i]} {task['text']} — could not schedule")

        header = get_message("morning_plan_sessions_created", user_lang)
        sessions_list = "\n".join(lines)
        await context.bot.send_message(
            chat_id=user_id,
            text=f"{header}\n\n{sessions_list}",
            parse_mode="Markdown",
        )
    
    async def _handle_add_to_calendar_no(self, query, user_lang: Language):
        """Handle user declining session planning."""
        await query.answer("Got it! You can plan sessions anytime from the app. Have a great day! 💪")

    async def _handle_plan_morning_session(self, query, idx: int, user_lang: Language):
        """Create a single planned session from the morning proposals."""
        user_id = query.from_user.id
        proposals = self.application.bot_data.get('morning_sessions_proposed', {}).get(user_id, [])
        if idx >= len(proposals):
            await query.answer("Session info not found. Please try again tomorrow.")
            return
        task = proposals[idx]
        try:
            self.plan_keeper.add_plan_session(
                user_id=user_id,
                promise_id=task['promise_id'],
                title=task['text'],
                planned_start=task.get('planned_start'),
                planned_duration_min=task.get('duration_min'),
            )
            time_label = (task.get('planned_start') or '')[11:16]  # HH:MM
            dur = task.get('duration_min', '')
            detail = f" — {time_label}, {dur} min" if time_label and dur else ""
            await query.answer(f"✅ Planned!{detail}")
            # Mark the tapped button with a checkmark
            if query.message and query.message.reply_markup:
                new_rows = []
                for row in query.message.reply_markup.inline_keyboard:
                    new_row = []
                    for btn in row:
                        cd = getattr(btn, 'callback_data', '') or ''
                        if f"idx={idx}" in cd:
                            new_row.append(InlineKeyboardButton(
                                text=f"✅ {btn.text}",
                                callback_data=encode_cb("noop"),
                            ))
                        else:
                            new_row.append(btn)
                    new_rows.append(new_row)
                try:
                    await query.edit_message_reply_markup(
                        reply_markup=InlineKeyboardMarkup(new_rows),
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Failed to create plan session idx={idx} for user {user_id}: {e}")
            await query.answer("Sorry, couldn't create this session. Please try again.")

    async def _handle_add_content(
        self,
        query,
        user_id: int,
        content_id: Optional[str],
        url_id: Optional[str],
        user_lang: Language,
    ) -> None:
        """Add resolved content to user's library from inline callback."""
        try:
            from repositories.content_repo import ContentRepository
            from services.content_resolve_service import ContentResolveService

            content_repo = ContentRepository()
            resolved_content_id = content_id

            if not resolved_content_id and url_id and "content_urls" in self.application.bot_data:
                source_url = self.application.bot_data["content_urls"].get(url_id)
                if source_url:
                    resolver = ContentResolveService(content_repo=content_repo)
                    resolved = resolver.resolve(source_url)
                    resolved_content_id = resolved.get("content_id") or resolved.get("id")

            if not resolved_content_id:
                await query.answer("Could not resolve this content yet. Please share the link again.", show_alert=True)
                return

            existing = content_repo.get_user_content(str(user_id), str(resolved_content_id))
            if existing:
                confirmation = "ℹ️ This content is already in your library."
            else:
                content_repo.add_user_content(str(user_id), str(resolved_content_id))
                confirmation = "✅ Added to your contents."

            # Remove the add button after action to avoid duplicate taps.
            if query.message and query.message.reply_markup and query.message.reply_markup.inline_keyboard:
                new_rows = []
                for row in query.message.reply_markup.inline_keyboard:
                    filtered = [
                        button
                        for button in row
                        if not (
                            getattr(button, "callback_data", None)
                            and "a=add_content" in str(button.callback_data)
                        )
                    ]
                    if filtered:
                        new_rows.append(filtered)
                if new_rows:
                    await self.response_service.edit_message_reply_markup(
                        query,
                        reply_markup=InlineKeyboardMarkup(new_rows),
                    )

            await query.message.reply_text(confirmation)
            await query.answer("Done")
        except Exception as e:
            logger.error(f"Error adding content from callback for user {user_id}: {e}")
            await query.answer("Failed to add this content. Please try again.", show_alert=True)
    
    async def _handle_summarize_content(self, query, url: str, user_id: int, user_lang: Language):
        """Handle summarize content request."""
        try:
            # Answer callback to show we're processing
            await query.answer()
            
            # Send processing message
            summarizing_msg = get_message("content_summarizing", user_lang)
            processing_msg = await query.message.reply_text(summarizing_msg)
            
            # Get content metadata
            from services.content_service import ContentService
            content_service = ContentService()
            link_metadata = content_service.process_link(url)
            
            # Summarize using planner API
            summary = self.plan_keeper.summarize_content(user_id, url, link_metadata)
            
            # Format and send summary
            summary_msg = get_message("content_summary", user_lang, summary=summary)
            
            # Delete processing message
            try:
                await processing_msg.delete()
            except Exception:
                pass
            
            # Send summary
            await query.message.reply_text(summary_msg, parse_mode='Markdown')
        
        except Exception as e:
            logger.error(f"Error summarizing content for user {user_id}: {str(e)}")
            error_msg = get_message("error_general", user_lang, error=str(e))
            await query.message.reply_text(error_msg)

    async def _handle_youtube_transcript(
        self,
        query,
        context: CallbackContext,
        url: str,
        user_id: int,
        video_id: Optional[str],
        user_lang: Language,
    ) -> None:
        """Fetch and send the full YouTube caption transcript when available."""
        try:
            await query.answer()
            if not query.message:
                return

            processing_msg = await query.message.reply_text("Fetching transcript from YouTube captions...")

            from services.learning_pipeline.ingestors.youtube_ingestor import YouTubeIngestor

            ingestor = YouTubeIngestor()
            ingested = await asyncio.to_thread(ingestor.ingest, url, {})

            try:
                await processing_msg.delete()
            except Exception:
                pass

            if not ingested.metadata.get("captions_used"):
                await query.message.reply_text(
                    "No downloadable captions found for this video. "
                    "If you want a transcript anyway, it must be generated by transcription (ASR)."
                )
                return

            transcript_text = (ingested.text or "").strip()
            if not transcript_text:
                await query.message.reply_text("Captions were detected, but transcript text was empty.")
                return

            safe_vid = (video_id or "video").strip() if video_id else "video"
            if len(safe_vid) > 32 or not all(c.isalnum() or c in "_-" for c in safe_vid):
                safe_vid = "video"

            buf = io.BytesIO(transcript_text.encode("utf-8"))
            buf.name = f"youtube_transcript_{safe_vid}.txt"
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=InputFile(buf),
                caption="Transcript (from captions)",
            )
        except Exception as e:
            logger.error("Error fetching YouTube transcript for user %s: %s", user_id, e)
            if query.message:
                error_msg = get_message("error_general", user_lang, error=str(e))
                await query.message.reply_text(error_msg)
    
    async def _generate_calendar_links_via_llm(self, top3_promises: list, user_now: datetime, 
                                               tzname: str, user_id: int, user_lang: Language) -> str:
        """Generate Google Calendar links via LLM for top 3 priorities."""
        from urllib.parse import quote
        
        # Get LLM handler from bot_data
        llm_handler = self.application.bot_data.get('llm_handler')
        if not llm_handler:
            raise ValueError("LLM handler not available")
        
        # Build prompt for LLM
        tasks_text = "\n".join([f"{i+1}. {p['text']}" for i, p in enumerate(top3_promises)])
        current_date_str = user_now.strftime("%Y-%m-%d")
        current_time_str = user_now.strftime("%H:%M")
        
        prompt = f"""You are helping create Google Calendar events for a user's top 3 priorities today.

Tasks:
{tasks_text}

User timezone: {tzname}
Current date: {current_date_str}
Current time: {current_time_str}

For each task, propose:
- A reasonable start time (considering it's morning, around 8:30 AM or later)
- A reasonable duration based on the task nature (e.g., exercise might be 30-60 min, deep work might be 2-3 hours)
- Generate a Google Calendar URL using this format:
https://calendar.google.com/calendar/render?action=TEMPLATE&text={{title}}&dates={{start_YYYYMMDDTHHmmss}}/{{end_YYYYMMDDTHHmmss}}&details={{description}}

Important:
- Dates must be in ISO 8601 format: YYYYMMDDTHHmmss (use Z for UTC or include timezone offset)
- For timezone-aware dates, use format like: 20240115T083000+0100 (if timezone offset is +1)
- URL encode all parameters (title, description)
- Use today's date: {current_date_str}

Return the result in Telegram markdown format with hyperlinks:
[Task Name](google_calendar_url)

Format as a numbered list with emojis (1️⃣, 2️⃣, 3️⃣).

Example format:
1️⃣ [Exercise regularly](https://calendar.google.com/calendar/render?action=TEMPLATE&text=Exercise%20regularly&dates=20240115T083000Z/20240115T093000Z&details=Morning%20workout)
2️⃣ [Deep work](https://calendar.google.com/calendar/render?action=TEMPLATE&text=Deep%20work&dates=20240115T093000Z/20240115T120000Z&details=Focus%20time)
3️⃣ [Study English](https://calendar.google.com/calendar/render?action=TEMPLATE&text=Study%20English&dates=20240115T140000Z/20240115T150000Z&details=Language%20practice)

Generate the calendar links now:"""
        
        # Get user language code
        user_lang_code = user_lang.value if user_lang else "en"
        
        # Call LLM
        response = llm_handler.get_response_custom(prompt, str(user_id), user_language=user_lang_code)
        
        return response
    
    async def _handle_broadcast_schedule(self, query, context: CallbackContext, user_lang: Language):
        """Handle broadcast schedule button click - transition to time input state."""
        user_id = query.from_user.id
        
        # Update state to waiting for time
        if 'user_data' not in context:
            context.user_data = {}
        context.user_data['broadcast_state'] = 'waiting_time'
        
        # Get admin timezone
        admin_tz = self.get_user_timezone(user_id) or "UTC"
        
        # Prompt for time input
        prompt_msg = (
            f"📅 **Schedule Broadcast**\n\n"
            f"Please enter the time for the broadcast:\n\n"
            f"• **ISO format**: `YYYY-MM-DD HH:MM` (e.g., 2024-01-15 14:30)\n"
            f"• **Natural language**: `tomorrow 2pm`, `in 1 hour`, etc.\n\n"
            f"⏰ Your timezone: `{admin_tz}`"
        )
        
        await query.edit_message_text(prompt_msg, parse_mode='Markdown')
    
    async def _handle_broadcast_cancel(self, query, context: CallbackContext, user_lang: Language):
        """Handle broadcast cancel button click - clear state and cancel."""
        # Clear broadcast state
        if 'user_data' in context:
            context.user_data.pop('broadcast_state', None)
            context.user_data.pop('broadcast_message', None)
            context.user_data.pop('broadcast_admin_id', None)
        
        cancel_msg = "❌ Broadcast cancelled."
        await query.edit_message_text(cancel_msg)
    
    async def _handle_suggestion_accept(self, query, suggestion_id: str, user_lang: Language):
        """Handle accepting a promise suggestion - create the promise for the user."""
        user_id = query.from_user.id
        
        try:
            from repositories.suggestions_repo import SuggestionsRepository
            from repositories.templates_repo import TemplatesRepository
            import json
            
            suggestions_repo = SuggestionsRepository()
            
            # Get the suggestion
            suggestion = suggestions_repo.get_suggestion(suggestion_id)
            if not suggestion:
                await query.edit_message_text("❌ Suggestion not found or already processed.")
                return
            
            # Verify this user is the recipient
            if str(suggestion['to_user_id']) != str(user_id):
                await query.edit_message_text("❌ You are not authorized to respond to this suggestion.")
                return
            
            # Check if already processed
            if suggestion['status'] != 'pending':
                await query.edit_message_text(f"ℹ️ This suggestion was already {suggestion['status']}.")
                return
            
            # Determine promise text and hours per week
            promise_text = None
            hours_per_week = 0.0
            if suggestion.get('template_id'):
                templates_repo = TemplatesRepository()
                template = templates_repo.get_template(suggestion['template_id'])
                if template:
                    promise_text = template.get('title', 'Untitled Promise')
                    # Use template's target_value and metric_type
                    target_value = template.get('target_value', 0)
                    metric_type = template.get('metric_type', 'count')
                    
                    if metric_type == 'hours':
                        hours_per_week = float(target_value)
                    else:
                        hours_per_week = 0.0  # Check-based for count metrics
            elif suggestion.get('draft_json'):
                try:
                    draft = json.loads(suggestion['draft_json'])
                    promise_text = draft.get('freeform_text', 'Custom Promise')
                    hours_per_week = 0.0  # Freeform suggestions are check-based
                except:
                    promise_text = 'Custom Promise'
                    hours_per_week = 0.0
            
            if not promise_text:
                promise_text = 'Suggested Promise'
            
            # Create the promise for the user with proper hours
            result = self.plan_keeper.add_promise(
                user_id=user_id,
                promise_text=promise_text,
                num_hours_promised_per_week=hours_per_week,
                recurring=True
            )
            
            # Update suggestion status
            suggestions_repo.update_suggestion_status(suggestion_id, 'accepted', str(user_id))
            
            # Get sender name for notification
            from repositories.settings_repo import SettingsRepository
            settings_repo = SettingsRepository()
            sender_settings = settings_repo.get_settings(int(suggestion['from_user_id']))
            sender_name = sender_settings.first_name or sender_settings.username or f"User {suggestion['from_user_id']}"
            
            # Update the message
            success_msg = (
                f"✅ **Promise accepted!**\n\n"
                f"📋 {promise_text}\n\n"
                f"Suggested by: {sender_name}\n\n"
                f"You can now track this promise in your dashboard!"
            )
            await query.edit_message_text(success_msg, parse_mode='Markdown')
            
            # Notify the sender that their suggestion was accepted
            try:
                receiver_name = settings_repo.get_settings(user_id).first_name or f"User {user_id}"
                notify_msg = f"🎉 Great news! {receiver_name} accepted your suggestion:\n\n📋 {promise_text}"
                await self.application.bot.send_message(
                    chat_id=int(suggestion['from_user_id']),
                    text=notify_msg
                )
            except Exception as e:
                logger.warning(f"Could not notify sender about accepted suggestion: {e}")
            
            logger.info(f"User {user_id} accepted suggestion {suggestion_id}")
            
        except Exception as e:
            logger.error(f"Error accepting suggestion {suggestion_id}: {e}")
            await query.edit_message_text("❌ Error accepting suggestion. Please try again.")
    
    async def _handle_suggestion_decline(self, query, suggestion_id: str, user_lang: Language):
        """Handle declining a promise suggestion."""
        user_id = query.from_user.id
        
        try:
            from repositories.suggestions_repo import SuggestionsRepository
            
            suggestions_repo = SuggestionsRepository()
            
            # Get the suggestion
            suggestion = suggestions_repo.get_suggestion(suggestion_id)
            if not suggestion:
                await query.edit_message_text("❌ Suggestion not found or already processed.")
                return
            
            # Verify this user is the recipient
            if str(suggestion['to_user_id']) != str(user_id):
                await query.edit_message_text("❌ You are not authorized to respond to this suggestion.")
                return
            
            # Check if already processed
            if suggestion['status'] != 'pending':
                await query.edit_message_text(f"ℹ️ This suggestion was already {suggestion['status']}.")
                return
            
            # Update suggestion status
            success = suggestions_repo.update_suggestion_status(suggestion_id, 'declined', str(user_id))
            
            if success:
                await query.edit_message_text("❌ Suggestion declined.")
                logger.info(f"User {user_id} declined suggestion {suggestion_id}")
            else:
                await query.edit_message_text("❌ Error declining suggestion. Please try again.")
                
        except Exception as e:
            logger.error(f"Error declining suggestion {suggestion_id}: {e}")
            await query.edit_message_text("❌ Error declining suggestion. Please try again.")
