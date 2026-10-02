"""Post confirmed Library shares to a club's Telegram group."""
import asyncio
import html
import json
import os
from urllib.parse import urljoin, urlencode

import httpx

from repositories.content_share_repo import ContentShareRepository
from services.object_storage_service import ObjectStorageService


async def _pdf_thumbnail_bytes(client: httpx.AsyncClient, storage_uri: str) -> bytes:
    storage = ObjectStorageService()
    if storage_uri.startswith("local://"):
        payload = await asyncio.to_thread(storage.resolve_local_storage_uri(storage_uri).read_bytes)
    else:
        signed_url, _ = storage.build_signed_get_url(storage_uri)
        response = await client.get(signed_url)
        response.raise_for_status()
        payload = response.content
    # Telegram photos have a 10 MB limit; a preview should be far smaller.
    if len(payload) > 10 * 1024 * 1024:
        raise ValueError("Thumbnail is too large for Telegram")
    return payload


def club_open_keyboard(path: str, label: str, base_url: str | None = None) -> dict:
    """Ask Telegram to authenticate the actual clicker, never the sharer."""
    base = (base_url or os.getenv('MINIAPP_URL') or 'https://xaana.club').rstrip('/') + '/'
    if path.startswith('/youtube-watch?') or path.startswith('/pdf-reader?'):
        login_url = urljoin(base, '/api/auth/telegram-open') + '?' + urlencode({'next': path})
        button = {'text': label, 'login_url': {'url': login_url}}
    else:
        button = {'text': label, 'url': urljoin(base, path)}
    return {'inline_keyboard': [[button]]}


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
    url = urljoin((os.getenv('MINIAPP_URL') or 'https://xaana.club').rstrip('/') + '/', reserved['path'])
    label = "باز کردن در زانا" if str(reserved.get("club_language") or "").startswith("fa") else "Open in Xaana"
    if not reserved['path'].startswith('/'):
        label = "باز کردن محتوا" if str(reserved.get("club_language") or "").startswith("fa") else "Open content"
    title = html.escape(str(reserved["title"]).strip()[:220])
    message = f'📚 <a href="{html.escape(url, quote=True)}">{title}</a>'
    keyboard = club_open_keyboard(reserved['path'], label)
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            photo_url = reserved.get("thumbnail_url")
            photo_bytes = None
            if reserved.get("thumbnail_storage_uri"):
                try:
                    photo_bytes = await _pdf_thumbnail_bytes(client, reserved["thumbnail_storage_uri"])
                except Exception:
                    # A missing preview must not prevent a member from opening the item.
                    pass
            if photo_url or photo_bytes:
                photo_fields = {"chat_id": reserved["chat_id"], "caption": message,
                                "parse_mode": "HTML", "reply_markup": keyboard}
                if photo_bytes:
                    response = await client.post(
                        f"https://api.telegram.org/bot{bot_token}/sendPhoto",
                        data={**photo_fields, "reply_markup": json.dumps(keyboard)},
                        files={"photo": ("preview.jpg", photo_bytes, "image/jpeg")},
                    )
                else:
                    response = await client.post(f"https://api.telegram.org/bot{bot_token}/sendPhoto",
                                                 json={**photo_fields, "photo": photo_url})
                payload = response.json()
                if response.status_code == 200 and payload.get("ok"):
                    message_id = int(payload["result"]["message_id"])
                    repo.finish_club_share(content_id, club_id, message_id)
                    return {"already_shared": False, "club_name": reserved["club_name"], "path": reserved["path"]}

            # Telegram explicitly rejected the image, or this PDF has no preview.
            response = await client.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={
                "chat_id": reserved["chat_id"], "text": message,
                "parse_mode": "HTML", "disable_web_page_preview": True,
                "reply_markup": keyboard,
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
