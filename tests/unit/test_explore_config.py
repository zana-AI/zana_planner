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
