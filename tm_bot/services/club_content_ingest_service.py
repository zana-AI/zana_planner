"""Import links posted by members through the normal resolver and club share flow."""
import asyncio
from urllib.parse import urlparse

from repositories.clubs_repo import ClubsRepository
from repositories.content_repo import ContentRepository
from services.content_resolve_service import ContentResolveService
from services.content_service import URL_PATTERN
from services.content_share_service import share_content_with_club


def group_content_urls(message_text: str, message=None, miniapp_url="https://xaana.club") -> list[str]:
    """Include Telegram text links, but don't reimport app links or group invites."""
    urls = URL_PATTERN.findall(message_text or "")
    for entity in getattr(message, "entities", None) or []:
        if getattr(entity, "type", None) == "text_link" and getattr(entity, "url", None):
            urls.append(entity.url)
    app_host = urlparse(miniapp_url).hostname
    result = []
    for url in urls:
        url = url.rstrip(".,;!?)\u060c\u061b")
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not host:
            continue
        if host in {app_host, "xaana.club", "www.xaana.club", "t.me", "telegram.me"}:
            continue
        if url not in result:
            result.append(url)
    return result


async def ingest_club_links(urls: list[str], club_id: str, user_id: int,
                            resolver=None, content_repo=None, clubs_repo=None) -> list[dict]:
    """Membership is checked before any fetch; the share reservation dedupes posts."""
    clubs_repo = clubs_repo or ClubsRepository()
    if not await asyncio.to_thread(clubs_repo.is_member, club_id, user_id):
        raise PermissionError("Join this club before sharing with it")
    content_repo = content_repo or ContentRepository()
    resolver = resolver or ContentResolveService(content_repo)
    results = []
    for url in urls:
        content = await asyncio.to_thread(resolver.resolve, url)
        content_id = str(content.get("content_id") or content["id"])
        # The poster is already using the item. Saving is idempotent and also
        # queues captions; other members see the sent share via membership.
        await asyncio.to_thread(content_repo.add_user_content, str(user_id), content_id)
        results.append(await share_content_with_club(content_id, club_id, str(user_id)))
    return results
