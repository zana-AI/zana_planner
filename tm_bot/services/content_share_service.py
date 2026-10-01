"""Post confirmed Library shares to a club's Telegram group."""
import os

import httpx

from repositories.content_share_repo import ContentShareRepository


async def share_content_with_club(content_id: str, club_id: str, user_id: str,
                                  repo: ContentShareRepository | None = None) -> dict:
    repo = repo or ContentShareRepository()
    reserved = repo.reserve_club_share(content_id, club_id, user_id)
    if reserved["already_shared"]:
        return {"already_shared": True, "club_name": reserved["club_name"]}

    bot_token = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        repo.fail_club_share(content_id, club_id)
        raise RuntimeError("Xaana bot is unavailable")
    url = f"{(os.getenv('MINIAPP_URL') or 'https://xaana.club').rstrip('/')}{reserved['path']}"
    label = "باز کردن در زانا" if str(reserved.get("club_language") or "").startswith("fa") else "Open in Xaana"
    title = str(reserved["title"]).strip()[:250]
    message = f"📚 {title}\n{url}"
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={
                "chat_id": reserved["chat_id"],
                "text": message,
                "disable_web_page_preview": False,
                "reply_markup": {"inline_keyboard": [[{"text": label, "url": url}]]},
            })
        payload = response.json()
        if response.status_code != 200 or not payload.get("ok"):
            repo.fail_club_share(content_id, club_id)
            raise RuntimeError("Xaana could not post to this club's Telegram group")
        message_id = int(payload["result"]["message_id"])
    except RuntimeError:
        raise
    except Exception as exc:
        # A timeout may have happened after Telegram accepted the message.
        # Keep the pending reservation to avoid immediate duplicate posts.
        raise RuntimeError("Telegram delivery could not be confirmed. Try again shortly.") from exc
    repo.finish_club_share(content_id, club_id, message_id)
    return {"already_shared": False, "club_name": reserved["club_name"], "path": reserved["path"]}
