from pathlib import Path

import httpx

from services.explore_config import ExploreConfigLoader


def test_published_view_sorts_and_filters_nodes(tmp_path: Path):
    config = tmp_path / "explore.yaml"
    config.write_text(
        """
version: 1
categories:
  - id: hidden
    title: Hidden
    published: false
  - id: second
    title: Second
    order: 20
    topics: []
  - id: first
    title: First
    order: 10
    topics:
      - id: hidden-topic
        title: Hidden topic
        published: false
      - id: topic
        title: Topic
        order: 1
        items:
          - id: hidden-item
            title: Hidden item
            published: false
          - id: z-item
            title: Z item
            order: 20
          - id: a-item
            title: A item
            order: 10
""",
        encoding="utf-8",
    )

    catalog = ExploreConfigLoader(config, cache_ttl_seconds=0).load()

    assert [category.id for category in catalog.categories] == ["first", "second"]
    assert [topic.id for topic in catalog.categories[0].topics] == ["topic"]
    assert [item.id for item in catalog.categories[0].topics[0].items] == ["a-item", "z-item"]


def test_remote_failure_falls_back_to_local(tmp_path: Path, monkeypatch):
    config = tmp_path / "explore.yaml"
    config.write_text("version: 1\ncategories: []\n", encoding="utf-8")
    monkeypatch.setenv("EXPLORE_CONFIG_URL", "https://content.example/explore.yaml")
    monkeypatch.setattr(
        "services.explore_config.httpx.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ConnectError("offline")),
    )

    assert ExploreConfigLoader(config, cache_ttl_seconds=0).load().categories == []


def test_invalid_yaml_does_not_replace_last_known_good_catalog(tmp_path: Path):
    config = tmp_path / "explore.yaml"
    config.write_text("version: 1\ncategories: []\n", encoding="utf-8")
    loader = ExploreConfigLoader(config, cache_ttl_seconds=0)
    assert loader.load().version == 1
    config.write_text("categories: [\n", encoding="utf-8")

    assert loader.load().categories == []


def test_approved_starter_catalog_contains_four_public_videos_without_cache_claims():
    path = Path(__file__).resolve().parents[2] / 'tm_bot/config/explore.yaml'
    catalog = ExploreConfigLoader._parse(path.read_text(encoding='utf-8')).published_view()
    expected = {
        'video-jamy-baguette': ('fr', 'vMIed3rlZtg', 460),
        'video-easy-french-happiness': ('fr', 'flS3MVNXWbw', 535),
        'video-ted-ed-procrastination': ('en', 'FWTNMzK9vG4', 345),
        'video-ted-ed-music-brain': ('en', 'R0JKCYZ8hng', 285),
    }
    starters = {
        item.id: (category.language, item)
        for category in catalog.categories
        for topic in category.topics
        for item in topic.items if item.starter
    }
    assert set(starters) == set(expected)
    for key, (language, video_id, duration) in expected.items():
        actual_language, item = starters[key]
        assert actual_language == language
        assert item.type == 'video' and item.published
        assert item.native_ref == f'/youtube-watch?video_id={video_id}'
        assert item.image == f'https://img.youtube.com/vi/{video_id}/mqdefault.jpg'
        assert item.duration_seconds == duration
        assert item.creator
        assert 'subtitles_available' not in item.model_dump()
    all_ids = {item.id for category in catalog.categories for topic in category.topics for item in topic.items}
    assert {'video-spoken-french-masterclass', 'video-whats-in-my-bag'} <= all_ids


def test_official_friends_clips_have_verified_metadata_not_invented_caption_readiness():
    path = Path(__file__).resolve().parents[2] / 'tm_bot/config/explore.yaml'
    catalog = ExploreConfigLoader._parse(path.read_text(encoding='utf-8')).published_view()
    english = next(category for category in catalog.categories if category.id == 'english')
    videos = {item.id: item for topic in english.topics for item in topic.items}
    for key, video_id, duration in [
        ('video-friends-joey-food', 'dGLObch14e4', 169),
        ('video-friends-pivot', 'UJHa8Bjjy1k', 289),
    ]:
        item = videos[key]
        assert item.creator == 'Friends · Official channel'
        assert item.native_ref == f'/youtube-watch?video_id={video_id}'
        assert item.duration_seconds == duration
        assert not item.starter
        assert 'subtitles_available' not in item.model_dump()
