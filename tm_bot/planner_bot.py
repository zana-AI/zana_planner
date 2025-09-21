import os
import subprocess
from urllib.parse import uses_relative
import asyncio
from datetime import datetime, timedelta, time
import logging
import logging.config

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackContext,
    filters,
    CallbackQueryHandler,
)
from telegram.request import HTTPXRequest
from llm_handler import LLMHandler
from models.models import Action
from services.planner_api_adapter import PlannerAPIAdapter
from utils.time_utils import beautify_time, round_time, get_week_range
from ui.messages import nightly_card_text, weekly_report_text, promise_report_text
from ui.keyboards import nightly_card_kb, weekly_report_kb, time_options_kb, pomodoro_kb, delete_confirmation_kb, \
    session_adjust_kb, session_finish_confirm_kb, session_paused_kb, session_running_kb, preping_kb
from cbdata import encode_cb, decode_cb
from infra.scheduler import schedule_user_daily
from zana_planner.tm_bot.utils_storage import create_user_directory

try:
    from zoneinfo import ZoneInfo
    from timezonefinder import TimezoneFinder
except ImportError:
    print("Error: Make sure all packages are installed: `pip install timezonefinder tzdata`")

class PlannerTelegramBot:
    def __init__(self, token: str, root_dir: str):
        request = HTTPXRequest(connect_timeout=10, read_timeout=20)
        self.application = Application.builder().token(token).build()
        self.llm_handler = LLMHandler()  # Instantiate the LLM handler
        self.plan_keeper = PlannerAPIAdapter(root_dir)  # Instantiate the PlannerAPI adapter
        self.root_dir = root_dir

        # Register handlers
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("promises", self.list_promises))  # list_promises command handler
        self.application.add_handler(CommandHandler("nightly", self.nightly_reminders))  # nightly command handler
        self.application.add_handler(CommandHandler("morning", self.morning_reminders))
        self.application.add_handler(CommandHandler("weekly", self.weekly_report))  # weekly command handler
        self.application.add_handler(CommandHandler("zana", self.plan_by_zana))  # zana command handler
        self.application.add_handler(CommandHandler("pomodoro", self.pomodoro))  # pomodoro command handler
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_handler(CallbackQueryHandler(self.handle_promise_callback))
        self.application.add_handler(CommandHandler("settimezone", self.cmd_settimezone))
        self.application.add_handler(MessageHandler(filters.LOCATION, self.on_location_shared))

    def get_user_timezone(self, user_id: int) -> str:
        """Get user timezone using the settings repository."""
        settings = self.plan_keeper.settings_repo.get_settings(user_id)
        return settings.timezone

    def set_user_timezone(self, user_id: int, tzname: str) -> None:
        """Set user timezone using the settings repository."""
        settings = self.plan_keeper.settings_repo.get_settings(user_id)
        settings.timezone = tzname
        self.plan_keeper.settings_repo.save_settings(settings)

    def bootstrap_schedule_existing_users(self):
        """
        On bot startup, (re)schedule nightly jobs for all existing users found under root_dir.
        Safe to run multiple times; it removes any prior job with the same name first.
        """
        jq = self.application.job_queue
        for entry in os.listdir(self.root_dir):
            user_path = os.path.join(self.root_dir, entry)
            if not os.path.isdir(user_path):
                continue
            try:
                user_id = int(entry)
            except ValueError:
                continue

            tzname = self.get_user_timezone(user_id) or "UTC"

            # make it idempotent
            job_name = f"nightly-{user_id}"
            for j in jq.get_jobs_by_name(job_name):
                j.schedule_removal()

            schedule_user_daily(
                jq,
                user_id=user_id,
                tz=tzname,
                callback=self.scheduled_morning_reminders_for_one,
                hh=8, mm=30,
                name_prefix="morning",
            )

            schedule_user_daily(
                jq,
                user_id=user_id,
                tz=tzname,
                callback=self.scheduled_nightly_reminders_for_one,
                hh=22, mm=59,
                name_prefix="nightly",
            )

    async def cmd_settimezone(self, update, context):
        user_id = update.effective_user.id
        if context.args:
            tzname = context.args[0]
            # validate
            try:
                ZoneInfo(tzname)
            except Exception:
                await update.message.reply_text(
                    "Invalid timezone. Example: /settimezone Europe/Paris"
                )
                return
            # save
            settings = self.plan_keeper.settings_repo.get_settings(user_id)
            settings.timezone = tzname
            self.plan_keeper.settings_repo.save_settings(settings)
            # reschedule nightly/morning jobs if you have them
            await self._reschedule_user_jobs(user_id, tzname)
            await update.message.reply_text(f"Timezone set to {tzname}")
            return

        # Ask for location
        kb = ReplyKeyboardMarkup(
            [[KeyboardButton("Share location", request_location=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
            input_field_placeholder="Tap to share your location…",
        )
        await update.message.reply_text(
            "Please share your location once so I can set your timezone.",
            reply_markup=kb,
        )

    async def on_location_shared(self, update, context):
        user_id = update.effective_user.id
        loc = update.effective_message.location
        if not loc:
            return

        tf = TimezoneFinder()
        tzname = tf.timezone_at(lat=loc.latitude, lng=loc.longitude)
        if not tzname:
            await update.message.reply_text(
                "Sorry, I couldn't detect your timezone. "
                "You can set it manually, e.g. /settimezone Europe/Paris",
                reply_markup=ReplyKeyboardRemove(),
            )
            return

        settings = self.plan_keeper.settings_repo.get_settings(user_id)
        settings.timezone = tzname
        self.plan_keeper.settings_repo.save_settings(settings)

        # await self._reschedule_user_jobs(user_id, tzname)

        await update.message.reply_text(
            f"Timezone set to {tzname}. I’ll schedule reminders in your local time.",
            reply_markup=ReplyKeyboardRemove(),
        )

    async def handle_promise_callback(self, update: Update, context: CallbackContext) -> None:
        """
        Handle the callback when a user selects or adjusts the time spent, or performs other actions on promises.
        """
        query = update.callback_query
        await query.answer()
        cb = decode_cb(query.data)
        current_s = cb.get("c")  # string or None
        user_id = query.from_user.id

        # Parse the callback data using new format
        cb = decode_cb(query.data)
        action = cb.get("a")
        promise_id = cb.get("p")
        value = cb.get("v")

        if action == "pomodoro_start":
            await self.start_pomodoro_timer(query, context)
        elif action == "pomodoro_pause":
            await query.edit_message_text(
                text="Pomodoro Timer Paused.",
                parse_mode='Markdown'
            )
        elif action == "pomodoro_stop":
            await query.edit_message_text(
                text="Pomodoro Timer Stopped.",
                parse_mode='Markdown'
            )

        if action == "remind_next_week":
            # Update the promise's start date to the beginning of next week
            next_monday = (datetime.now() + timedelta(days=(7 - datetime.now().weekday()))).date()
            self.plan_keeper.update_promise_start_date(query.from_user.id, promise_id, next_monday)
            await query.edit_message_text(
                text=f"#{promise_id} will be silent until monday.",
                parse_mode='Markdown'
            )
            return

        elif action == "delete_promise":
            # Retrieve the current keyboard from the message
            keyboard = list(query.message.reply_markup.inline_keyboard)  # Convert tuple to list
            # Add confirmation buttons to the second row
            confirm_buttons = [
                InlineKeyboardButton("Yes (delete)", callback_data=encode_cb("confirm_delete", pid=promise_id)),
                InlineKeyboardButton("No (cancel)", callback_data=encode_cb("cancel_delete", pid=promise_id)),
            ]
            # Keep the first row and add the confirmation buttons as a new row
            keyboard.append(confirm_buttons)
            await query.edit_message_text(
                text=query.message.text_markdown,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return

        elif action == "confirm_delete":
            # Delete the promise after confirmation
            result = self.plan_keeper.delete_promise(query.from_user.id, promise_id)
            await query.edit_message_text(
                text=result,
                parse_mode='Markdown'
            )
            return

        elif action == "cancel_delete":
            # Cancel the delete action
            await query.edit_message_text(
                text=query.message.text_markdown,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(query.message.reply_markup.inline_keyboard[:-1])

            )
            return

        elif action == "report_promise":
            # Generate a report for the promise
            report = self.plan_keeper.get_promise_report(query.from_user.id, promise_id)
            await query.edit_message_text(
                text=report,
                parse_mode='Markdown'
            )
            return

        # Handle time-related actions
        elif action == "update_time_spent" and value is not None:
            try:
                curr = float(current_s or 0.0)
            except Exception:
                curr = 0.0
            delta = float(value)
            if curr <= 0.5:
                new_curr = max(0.0, round_time(curr + delta, step_min=5))
            else:
                new_curr = round_time(curr + delta, step_min=15)

            base_h=0
            try:
                old_cb_data = query.message.reply_markup.inline_keyboard[0][1].callback_data
                old_cb_dict = old_cb_data.split("&")
                old_time = [float(pd[2:]) for pd in old_cb_dict if pd.startswith("v=")]
                base_h = old_time[0] if old_time else 0.0
            except Exception:
                pass

            last = self.plan_keeper.get_last_action_on_promise(user_id, promise_id)
            last_h = float(getattr(last, "time_spent", 0.0) or 0.0)

            kb = time_options_kb(promise_id, new_curr, base_h)
            await query.edit_message_reply_markup(reply_markup=kb)
            await query.answer(f"{beautify_time(new_curr)} selected")
            return

        elif action == "time_spent" and value is not None:
            # When a valid time option is selected (greater than 0), register the action.
            if value > 0:
                # Register the action
                self.plan_keeper.add_action(
                    user_id=query.from_user.id,
                    promise_id=promise_id,
                    time_spent=value,
                    action_datetime=query.message.date
                )
                await query.edit_message_text(
                    text=f"Spent {beautify_time(value)} on #{promise_id}.",
                    parse_mode='Markdown'
                )
            else:
                # If 0 is selected, consider it a cancellation and delete the message.
                await query.delete_message()

        elif action == "show_more":
            user_id = update.effective_user.id
            tzname = self.get_user_timezone(user_id)
            user_now = datetime.now(ZoneInfo(tzname))

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
                await query.edit_message_text("✅ That’s all for today.")
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
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"How much time did you spend today on *{p.text}*?",
                    reply_markup=kb,
                    parse_mode="Markdown",
                )

            # update the header's button (this callback came from that message)
            new_offset = offset + len(chunk)
            remaining = max(0, total - new_offset)
            if remaining > 0:
                await query.edit_message_reply_markup(
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            f"Show more ({remaining})",
                            callback_data=encode_cb("show_more", o=new_offset, n=batch)
                        )
                    ]])
                )
            else:
                await query.edit_message_text("✅ That’s all for today.")
            return

        # in handle_promise_callback
        elif action == "session_start":
            user_id = update.effective_user.id
            # If SessionsService exists:
            # sess = self.plan_keeper.sessions_service.start(user_id, promise_id)
            await query.answer("Timer started")
            # (optional) edit message to show a “running” status or send a new session card
            return

        cb = decode_cb(query.data)
        a, p, s = cb.get("a"), cb.get("p"), cb.get("s")
        v = cb.get("v")
        m = cb.get("m")  # minutes for snooze
        user_id = query.from_user.id
        user_now, _tzname = self._get_user_now(user_id)

        # === Pre-ping ===
        if a == "preping_start":
            # create session, start ticker, swap to running UI
            sess = self.plan_keeper.sessions_service.start(user_id, p)  # returns Session (with session_id)
            # persist message_id so ticker can edit this message
            await query.edit_message_text(
                text=self._session_text(sess, elapsed="00:00:00"),
                reply_markup=session_running_kb(sess.session_id),
                parse_mode="Markdown",
            )
            self._schedule_session_ticker(sess)  # run_repeating every 5–15s
            return

        if a == "preping_skip":
            # mark skip (optional: append Action with 0h & action="skip_today")
            self.plan_keeper.actions_repo.append_action(
                Action(user_id=user_id, promise_id=p, action="skip", time_spent=0.0, at=user_now)
            )
            await query.edit_message_text("Noted. We’ll skip this one today. ✅")
            return

        if a == "preping_snooze":
            minutes = int(m or 30)
            when = user_now + timedelta(minutes=minutes)
            self._schedule_one_pre_ping(user_id, p, when)  # helper added below
            await query.edit_message_text(f"#{p.title()} snoozed for {minutes}m. ⏰")
            return

        if a == "open_time":
            promise = self.plan_keeper.get_promise(user_id, p)
            weekly_h = self._hours_per_week_of(promise)
            base_day_h = weekly_h / 7.0
            curr_h = self._last_hours_or(user_id, p, fallback=base_day_h)

            kb = time_options_kb(
                promise_id=p,
                curr_h=curr_h,
                base_day_h=base_day_h,
                weekly_h=weekly_h,
                show_timer=True,  # if you want the Start ⏱ row
            )
            await query.edit_message_reply_markup(reply_markup=kb)
            return

        # === Session lifecycle ===
        if a == "session_pause":
            sess = self.plan_keeper.sessions_service.pause(user_id, s)
            self._stop_ticker(s)  # stop repeating job
            await query.edit_message_reply_markup(reply_markup=session_paused_kb(s))
            return

        if a == "session_resume":
            sess = self.plan_keeper.sessions_service.resume(user_id, s)
            self._schedule_session_ticker(sess)
            await query.edit_message_reply_markup(reply_markup=session_running_kb(s))
            return

        if a == "session_plus":
            # bump the “effective elapsed” accounting inside the session
            self.plan_keeper.sessions_service.bump(user_id, s, float(v or 0.0))  # implement optional bump()
            await query.answer(f"Added {beautify_time(float(v))}")
            return

        if a == "session_snooze":
            minutes = int(m or 10)
            self.plan_keeper.sessions_service.pause(user_id, s)
            self._stop_ticker(s)
            self._schedule_session_resume(user_id, s, user_now + timedelta(minutes=minutes))
            await query.edit_message_reply_markup(reply_markup=session_paused_kb(s))
            await query.answer(f"Snoozed {minutes}m")
            return

        # === Finish flow ===
        if a == "session_finish_open":
            sess = self.plan_keeper.sessions_service.peek(user_id, s)  # read without finishing
            proposed_h = self._session_effective_hours(sess)
            await query.edit_message_reply_markup(reply_markup=session_finish_confirm_kb(s, proposed_h))
            return

        if a == "session_finish_confirm":
            logged = self.plan_keeper.sessions_service.finish(user_id, s, override_hours=float(v))
            self._stop_ticker(s)
            await query.edit_message_text(f"Logged {beautify_time(float(v))} for *{logged.promise_id}*. ✅",
                                          parse_mode="Markdown")
            return

        if a == "session_adjust_open":
            await query.edit_message_reply_markup(reply_markup=session_adjust_kb(s, base_h=float(v or 0.5)))
            return

        if a == "session_adjust_set":
            logged = self.plan_keeper.sessions_service.finish(user_id, s, override_hours=float(v))
            self._stop_ticker(s)
            await query.edit_message_text(f"Logged {beautify_time(float(v))}. ✅")
            return

    def _get_user_now(self, user_id: int):
        """Return (now_in_user_tz, tzname)."""
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
        last = self.plan_keeper.get_last_action_on_promise(user_id, promise_id)
        try:
            return float(getattr(last, "time_spent", fallback) or fallback)
        except Exception:
            return fallback

    def _schedule_one_pre_ping(self, user_id: int, promise_id: str, when_dt: datetime):
        """Schedule a single pre-ping message (Start / Not today / Snooze / More…)."""
        name = f"preping-{user_id}-{promise_id}-{int(when_dt.timestamp())}"
        # remove any previous job with the same name to keep idempotent
        for j in self.application.job_queue.get_jobs_by_name(name):
            j.schedule_removal()
        self.application.job_queue.run_once(
            self.pre_ping_one, when=when_dt,
            data={"user_id": user_id, "promise_id": promise_id},
            name=name,
        )

    def _schedule_session_ticker(self, sess):  # TODO: implement later
        return

    def _stop_ticker(self, session_id: str):  # TODO: implement later
        return

    def _session_text(self, sess, elapsed: str) -> str:
        return (f"⏱ *Session for #{sess.promise_id}: {self.plan_keeper.promises_repo.get_promise(sess.user_id, sess.promise_id).text}*"
                f"\nStarted {sess.started_at.strftime('%H:%M')} | Elapsed: {elapsed}")

    async def pre_ping_one(self, context):
        """Job callback: send the pre-ping card."""
        user_id = context.job.data["user_id"]
        promise_id = context.job.data["promise_id"]
        # resolve promise text
        p = self.plan_keeper.get_promise(user_id, promise_id)
        title = getattr(p, "text", None) or (p.get("text") if isinstance(p, dict) else f"#{promise_id}")
        await context.bot.send_message(
            chat_id=user_id,
            text=f"*{title}* — ready to start?",
            reply_markup=preping_kb(promise_id),  # from ui.keyboards
            parse_mode="Markdown",
        )

    async def send_nightly_reminders(self, context: CallbackContext, user_id=None) -> None:
        """
        Send nightly reminders to users about their promises using the new services.
        """
        # Determine which user directories to use.
        user_id_int = int(user_id)
        tzname = self.get_user_timezone(user_id_int)
        user_now = datetime.now(ZoneInfo(tzname))

        # get a bigger ranked list, then slice
        ranked = self.plan_keeper.reminders_service.select_nightly_top(user_id_int, user_now, n=1000)
        if not ranked:
            return

        top3, rest = ranked[:3], ranked[3:]

        # (optional) header message with "Show more"
        if rest:
            await context.bot.send_message(
                chat_id=user_id_int,
                text="🌙 *Nightly reminders*\nHere are today’s top 3. Tap “Show more” for additional suggestions.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        f"Show more ({len(rest)})",
                        callback_data=encode_cb("show_more", o=3, n=5)  # offset=3, batch=5
                    )
                ]]),
                parse_mode="Markdown",
            )
        else:
            await context.bot.send_message(
                chat_id=user_id_int,
                text="🌙 *Nightly reminders*",
                parse_mode="Markdown",
            )

        # send 3 separate messages with time options
        for p in top3:
            weekly_h = float(getattr(p, "hours_per_week", 0.0) or 0.0)
            base_day_h = weekly_h / 7.0
            last = self.plan_keeper.get_last_action_on_promise(user_id_int, p.id)
            curr_h = float(getattr(last, "time_spent", 0.0) or base_day_h)

            kb = time_options_kb(p.id, curr_h=curr_h, base_day_h=base_day_h, weekly_h=weekly_h)
            await context.bot.send_message(
                chat_id=user_id_int,
                text=f"How much time did you spend today on *{p.text}*?",
                reply_markup=kb,
                parse_mode="Markdown",
            )

    async def send_morning_reminders(self, context, user_id: int):
        user_id = int(user_id)
        tzname = self.get_user_timezone(user_id) or "UTC"
        user_now = datetime.now(ZoneInfo(tzname))

        # rank a larger list once, then slice top 3 (reuse your reminders_service)
        ranked = self.plan_keeper.reminders_service.select_nightly_top(user_id, user_now, n=1000)
        if not ranked:
            return

        top3 = ranked[:3]

        # header (different copy than nightly)
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "☀️ *Morning Focus*\n"
                "Here are the top 3 to prioritize today. Pick a quick time or adjust, then get rolling."
            ),
            parse_mode="Markdown",
        )

        # per-promise cards with choices
        for p in top3:
            weekly_h = float(getattr(p, "hours_per_week", 0.0) or 0.0)
            base_day_h = weekly_h / 7.0

            last = self.plan_keeper.get_last_action_on_promise(user_id, p.id)
            curr_h = float(getattr(last, "time_spent", 0.0) or base_day_h)

            await context.bot.send_message(
                chat_id=user_id,
                text=f"🌸 What about *{p.text}* today? Ready to start?",
                reply_markup=preping_kb(p.id, snooze_min=30),
                parse_mode="Markdown",
            )

    async def start(self, update: Update, _context: CallbackContext) -> None:
        """Send a message when the command /start is issued."""
        user_id = update.effective_user.id
        created = create_user_directory(self.root_dir,  user_id)
        if created:
            await update.message.reply_text('Hi! Welcome to plan keeper. Your user directory has been created.')
        else:
            await update.message.reply_text('Hi! Welcome back.')

        tzname = self.get_user_timezone(user_id)
        schedule_user_daily(
            self.application.job_queue,
            user_id=user_id,
            tz=tzname,
            callback=self.scheduled_morning_reminders_for_one,
            hh=8, mm=30,
            name_prefix="morning",
        )

        # (Re)Schedule this user's nightly job at 22:59 in their timezone
        schedule_user_daily(
            self.application.job_queue,
            user_id,
            tzname,
            self.scheduled_nightly_reminders_for_one,
            hh=22,
            mm=59,
            name_prefix="nightly"
        )
        logger.info(f"Scheduled nightly reminders at 22:59 {tzname} for user {user_id}")

    async def scheduled_nightly_reminders_for_one(self, context: CallbackContext) -> None:
        user_id = context.job.data["user_id"]
        logger.info(f"Running scheduled nightly reminder for user {user_id}")
        await self.send_nightly_reminders(context, user_id=user_id)

    async def scheduled_morning_reminders_for_one(self, context):
        user_id = context.job.data["user_id"]
        await self.send_morning_reminders(context, user_id=user_id)

    async def list_promises(self, update: Update, _context: CallbackContext) -> None:
        """Send a message listing all promises for the user."""
        user_id = update.effective_user.id
        promises = self.plan_keeper.get_promises(user_id)
        if not promises:
            await update.message.reply_text("You have no promises. You want to add one? For example, you could promise to "
                                            "'deep work 6 hours a day, 5 days a week', "
                                            "'spend 2 hours a week on playing guitar.'")
        else:
            formatted_promises = ""
            # Sort promises by promise_id
            sorted_promises = sorted(promises, key=lambda p: p['id'])
            for index, promise in enumerate(sorted_promises):
                # Numerize and format promises
                promised_hours = promise['hours_per_week']
                promise_progress = self.plan_keeper.get_promise_weekly_progress(user_id, promise['id'])
                recurring = promise['recurring']
                # if not recurring:
                formatted_promises += f"* {promise['id']}: {promise['text'].replace('_', ' ')}\n"
                # formatted_promises += f"  - Progress: {promise_progress * 100:.1f}% ({promise_progress * promised_hours:.1f}/{promised_hours} hours)\n"

            # formatted_promises = "\n".join([f"* #{promise['id']}: {promise['text'].replace('_', ' ')}" for index, promise in enumerate(sorted_promises)])
            await update.message.reply_text(f"Your promises:\n{formatted_promises}")

    async def nightly_reminders(self, update: Update, _context: CallbackContext) -> None:
        """Handle the /nightly command to send nightly reminders."""
        uses_id = update.effective_user.id
        await self.send_nightly_reminders(_context, user_id=uses_id)
        # await update.message.reply_text("Nightly reminders sent!")

    async def morning_reminders(self, update, context):
        await self.send_morning_reminders(context, user_id=update.effective_user.id)

    async def weekly_report(self, update: Update, _context: CallbackContext) -> None:
        """Handle the /weekly command to send a weekly report with a refresh button."""
        user_id = update.effective_user.id
        report_ref_time = datetime.now()

        # Get weekly summary using the new service
        summary = self.plan_keeper.reports_service.get_weekly_summary(user_id, report_ref_time)
        report = weekly_report_text(summary)

        # Compute week boundaries based on report_ref_time.
        week_start, week_end = get_week_range(report_ref_time)
        date_range_str = f"{week_start.strftime('%d %b')} - {week_end.strftime('%d %b')}"

        # Create refresh keyboard
        keyboard = weekly_report_kb(report_ref_time)

        await update.message.reply_text(
            f"Weekly: {date_range_str}\n\n{report}",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

    async def refresh_weekly_report(self, update: Update, context: CallbackContext) -> None:
        """Handle refresh callback to update the weekly report using the original reference time."""
        query = update.callback_query
        await query.answer()

        # Callback data format: "refresh_weekly:<user_id>:<ref_timestamp>"
        payload = decode_cb(query.data)
        if payload.get("a") != "weekly_refresh":
            return

        user_id = payload.get("p") or str(update.effective_user.id)
        ref_timestamp = int(payload["t"])  # ensure keyboard passes 't'
        report_ref_time = datetime.fromtimestamp(ref_timestamp)

        report = self.plan_keeper.get_weekly_report(user_id, reference_time=report_ref_time)

        # Recompute the date range.
        week_start, week_end = get_week_range(report_ref_time)
        date_range_str = f"{week_start.strftime('%d %b')} - {week_end.strftime('%d %b')}"

        # Preserve the same refresh callback data.
        refresh_btn = InlineKeyboardButton("Refresh", callback_data=encode_cb("weekly_refresh", pid=str(user_id), t=str(ref_timestamp)))
        await query.edit_message_text(
            f"Weekly: {date_range_str}\n\n{report}",
            reply_markup=InlineKeyboardMarkup([[refresh_btn]]),
            parse_mode='Markdown'
        )

    async def plan_by_zana(self, update: Update, _context: CallbackContext) -> None:
        user_id = update.effective_user.id
        promises = self.plan_keeper.get_promises(user_id)

        if not promises:
            await update.message.reply_text("You have no promises to report on.")
            return

        # Generate reports for all promises
        reports = []
        for promise in promises:
            report = self.plan_keeper.get_promise_report(user_id, promise['id'])
            reports.append(report)

        # Concatenate all reports
        full_report = "\n\n".join(reports)

        # Create a creative prompt for the LLM
        prompt = (
            "Here is a detailed report of my current promises and progress:\n\n"
            f"'''{full_report}\n\n'''"
            f"And today is {datetime.now().strftime('%A %d-%B-%Y %H:%M')}. "
            "Based on this report, please provide insights on what the user should focus on today. "
            "Your response should follow a format similar to this example:\n\n"
            "--------------------------------------------------\n"
            "**Focus Areas + Actionable Steps for Today: [Date]**\n\n"
            "#### 1. [Promise Title]\n"
            "- Current Status: [current progress] (e.g., 10.0/30.0 hours this week, 33%).\n"
            "- Actionable Step: [Suggest a concrete step].\n\n"
            "#### 2. [Another Promise Title]\n"
            "- Current Status: [progress details].\n"
            "- Actionable Step: [Action recommendation].\n\n"
            "### Motivational Reminder\n"
            "Include a brief, uplifting message to encourage progress.\n\n"
            "### Today’s Focus Summary\n"
            "Summarize key focus areas and recommended time allocations.\n"
            "--------------------------------------------------\n\n"
            "Keep the tone creative, motivational, and succinct!"
        )

        # Get insights from the LLM handler
        insights = self.llm_handler.get_response_custom(prompt, user_id)

        # Send the insights to the user
        await update.message.reply_text(
            f"Insights from Zana:\n{insights}",
            parse_mode='Markdown'
        )

    async def handle_message(self, update: Update, _context: CallbackContext) -> None:
        try:
            user_message = update.message.text
            user_id = update.effective_user.id

            # Check if user exists, if not, call start
            user_dir = os.path.join(self.root_dir, str(user_id))
            if not os.path.exists(user_dir):
                await self.start(update, _context)

            llm_response = self.llm_handler.get_response_api(user_message, user_id)

            # Check for errors in LLM response
            if "error" in llm_response:
                await update.message.reply_text(
                    llm_response["response_to_user"],
                    parse_mode='Markdown'
                )
                return

            # Process the LLM response
            try:
                func_call_response = self.call_planner_api(user_id, llm_response)
                formatted_response = self._format_response(llm_response['response_to_user'], func_call_response)
                await update.message.reply_text(
                    formatted_response,
                    parse_mode='Markdown'
                )
            except ValueError as e:
                await update.message.reply_text(
                    f"⚠️ Invalid input: {str(e)}",
                    parse_mode='Markdown'
                )
                logger.error(f"Validation error for user {user_id}: {str(e)}")
            except Exception as e:
                await update.message.reply_text(
                    f"❌ Sorry, I couldn't complete that action. Please try again. Error: {str(e)}",
                    parse_mode='Markdown'
                )
                logger.error(f"Error processing request for user {user_id}: {str(e)}")

        except Exception as e:
            await update.message.reply_text(
                f"🔧 Something went wrong. Please try again later. Error: {str(e)}",
                parse_mode='Markdown'
            )
            logger.error(f"Unexpected error handling message from user {user_id}: {str(e)}")

    def _format_response(self, llm_response, func_call_response):
        """Format the response for Telegram."""
        try:
            if isinstance(func_call_response, list):
                formatted_response = "\n• " + "\n• ".join(str(item) for item in func_call_response)
            elif isinstance(func_call_response, dict):
                formatted_response = "\n".join(f"{key}: {value}" for key, value in func_call_response.items())
            else:
                formatted_response = str(func_call_response)

            full_response = f"*Zana:*\n`{llm_response}`\n\n"
            if formatted_response:
                full_response += f"*Log:*\n{formatted_response}"
            return full_response
        except Exception as e:
            logger.error(f"Error formatting response: {str(e)}")
            return "Error formatting response"

    def call_planner_api(self, user_id, llm_response: dict) -> str:
        """
        Process user message by sending it to the LLM and executing the identified action.
        """
        try:
            # Interpret LLM response (you'll need to customize this to match your LLM's output format)
            # Get the function name and arguments from the LLM response
            function_name = llm_response.get("function_call", None)
            if function_name is None:
                return ""

            func_args = llm_response.get("function_args", {})

            # Add user_id to function arguments
            func_args["user_id"] = user_id

            # Get the corresponding method from plan_keeper
            if hasattr(self.plan_keeper, function_name):
                method = getattr(self.plan_keeper, function_name)
                # Call the method with unpacked arguments
                return method(**func_args)
            else:
                return f"Function {function_name} not found in PlannerAPI"
        except Exception as e:
            return f"Error executing function: {str(e)}"
        return None

    def run(self):
        """Start the bot."""
        self.application.run_polling()

    async def pomodoro(self, update: Update, context: CallbackContext) -> None:
        """Handle the /pomodoro command to start a Pomodoro timer."""
        keyboard = pomodoro_kb()
        await update.message.reply_text(
            "Pomodoro Timer: 25:00",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

    async def start_pomodoro_timer(self, query, context):
        """Start the Pomodoro timer."""
        total_time = 25 # minutes
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

        await query.edit_message_text(
            text="Pomodoro Timer (25min) Finished! 🎉",
            parse_mode='Markdown'
        )
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Time's up! Take a break or start another session.",
            parse_mode='Markdown'
        )


if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv()
    ROOT_DIR = os.getenv("ROOT_DIR")
    ROOT_DIR = os.path.abspath(subprocess.check_output(f'echo {ROOT_DIR}', shell=True).decode().strip())
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    LOG_FILE = os.getenv("LOG_FILE", os.path.abspath(os.path.join(__file__, '../..', 'bot.log')))

    # Enable logging
    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
            },
        },
        'handlers': {
            'default': {
                'level': 'INFO',
                'formatter': 'standard',
                'class': 'logging.StreamHandler',
            },
            'file': {
                'level': 'INFO',
                'formatter': 'standard',
                'class': 'logging.FileHandler',
                'filename': LOG_FILE,
                'mode': 'a',
            },
        },
        'loggers': {
            '': {  # root logger
                'handlers': ['default', 'file'],
                'level': 'INFO',
                'propagate': True
            },
            'httpx': {  # httpx logger
                'handlers': ['default', 'file'],
                'level': 'WARNING',
                'propagate': True
            }
        }
    })

    logger = logging.getLogger(__name__)

    bot = PlannerTelegramBot(BOT_TOKEN, ROOT_DIR)
    bot.bootstrap_schedule_existing_users()
    bot.run()
