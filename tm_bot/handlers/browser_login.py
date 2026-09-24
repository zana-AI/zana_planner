"""Browser login deliberately avoids the remembered Telegram OAuth account."""
import asyncio
from urllib.parse import urlencode

from repositories.browser_login_repo import BrowserLoginRepository


async def send_browser_login(update, miniapp_url: str) -> None:
    # Never post sign-in credentials into a group or channel.
    if not update.effective_chat or update.effective_chat.type != "private":
        await update.effective_message.reply_text("Send /login in a private chat with me to sign in.")
        return
    user = update.effective_user
    if not user or user.is_bot:
        return
    code = await asyncio.to_thread(BrowserLoginRepository().issue, user.id)
    url = miniapp_url.rstrip("/") + "/login#" + urlencode({"code": code})
    # Send directly: no LLM translation or conversation logging of credentials.
    await update.effective_message.reply_text(
        f"Sign in to Xaana as {user.first_name} (Telegram ID: {user.id}).\n\n"
        "Open this link in the browser where you want to sign in, or copy it into "
        "Xaana's ‘Use another Telegram account’ screen:\n\n"
        f"{url}\n\n"
        "It works once and expires in 5 minutes. Only use links you requested yourself; "
        "never forward this link to anyone.",
        parse_mode=None,
        disable_web_page_preview=True,
    )
