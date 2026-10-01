"""No Telegram messages, metadata requests or database writes leave these tests."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from services import club_content_ingest_service as service
from repositories.content_share_repo import content_share_path
from utils.url_utils import canonicalize_url


def test_links_include_hidden_entities_and_skip_app_and_telegram_links():
    message = SimpleNamespace(entities=[SimpleNamespace(type='text_link', url='https://example.com/news')])
    assert service.group_content_urls(
        'https://youtu.be/YSHZ9TMvNHc, https://xaana.club/youtube-watch?video_id=YSHZ9TMvNHc '
        'https://t.me/+invite https://example.com/news', message) == [
            'https://youtu.be/YSHZ9TMvNHc', 'https://example.com/news']


def test_youtube_aliases_resolve_to_one_content_key():
    for url in ['https://youtu.be/YSHZ9TMvNHc?si=abc',
                'https://www.youtube.com/watch?v=YSHZ9TMvNHc&t=20',
                'https://m.youtube.com/watch?t=20&v=YSHZ9TMvNHc',
                'https://www.youtube.com/shorts/YSHZ9TMvNHc']:
        assert canonicalize_url(url) == 'https://www.youtube.com/watch?v=YSHZ9TMvNHc'


def test_member_post_uses_resolver_saves_poster_and_shares_to_only_that_club(monkeypatch):
    resolver = Mock(resolve=Mock(return_value={'content_id': 'item'}))
    content = Mock()
    clubs = Mock(is_member=Mock(return_value=True))
    share = AsyncMock(return_value={'already_shared': False})
    monkeypatch.setattr(service, 'share_content_with_club', share)
    result = asyncio.run(service.ingest_club_links(['https://example.com/news'], 'club-1', 42, resolver, content, clubs))
    clubs.is_member.assert_called_once_with('club-1', 42)
    resolver.resolve.assert_called_once_with('https://example.com/news')
    content.add_user_content.assert_called_once_with('42', 'item')
    share.assert_awaited_once_with('item', 'club-1', '42')
    assert result == [{'already_shared': False}]


def test_nonmember_cannot_import_or_share(monkeypatch):
    resolver, content = Mock(), Mock()
    share = AsyncMock()
    monkeypatch.setattr(service, 'share_content_with_club', share)
    with pytest.raises(PermissionError):
        asyncio.run(service.ingest_club_links(['https://example.com'], 'club', 42,
            resolver, content, Mock(is_member=Mock(return_value=False))))
    resolver.resolve.assert_not_called()
    content.add_user_content.assert_not_called()
    share.assert_not_awaited()


def test_article_share_keeps_its_source_and_video_share_keeps_club_context():
    assert content_share_path({'id': 'item', 'provider': 'blog', 'canonical_url': 'https://example.com/news'}, 'club') == 'https://example.com/news'
    path = content_share_path({'id': 'item', 'provider': 'youtube', 'metadata_json': {'video_id': 'YSHZ9TMvNHc'}}, 'club')
    assert path == '/youtube-watch?video_id=YSHZ9TMvNHc&content_id=item&club_id=club'
    with pytest.raises(ValueError):
        content_share_path({'id': 'item', 'canonical_url': 'javascript:alert(1)'}, 'club')


def test_group_text_link_bypasses_the_chat_responder(monkeypatch):
    from planner_bot import PlannerBot
    bot = object.__new__(PlannerBot)
    bot._record_group_visible_message = Mock()
    bot._handle_group_content_links = AsyncMock(return_value=True)
    ctx = SimpleNamespace(input_type='text')
    asyncio.run(bot._handle_group_input(ctx))
    bot._handle_group_content_links.assert_awaited_once_with(ctx)


def test_bot_posts_and_unconnected_groups_are_not_imported(monkeypatch):
    from planner_bot import PlannerBot
    bot = object.__new__(PlannerBot)
    bot._get_club_for_group_chat = Mock(return_value=None)
    ctx = SimpleNamespace(user_id=42, chat_id=-123, raw_text='https://example.com/news',
                          platform_update=SimpleNamespace(effective_user=SimpleNamespace(is_bot=True)))
    assert asyncio.run(bot._handle_group_content_links(ctx)) is False
    bot._get_club_for_group_chat.assert_not_called()
    ctx.platform_update.effective_user.is_bot = False
    assert asyncio.run(bot._handle_group_content_links(ctx)) is False
