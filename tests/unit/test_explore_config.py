"""Explore catalog projection and failure handling without live content files."""
from services.explore_config import ExploreConfigLoader


def test_published_view_sorts_and_filters_nodes():
    document = {
        "version": 1,
        "categories": [
            {"id": "hidden", "title": "Hidden", "published": False},
            {"id": "second", "title": "Second", "order": 20},
            {"id": "first", "title": "First", "order": 10, "topics": [
                {"id": "hidden-topic", "title": "Hidden", "published": False},
                {"id": "watch", "title": "Watch", "items": [
                    {"id": "hidden-item", "title": "Hidden", "published": False},
                    {"id": "z-item", "title": "Z", "order": 20},
                    {"id": "a-item", "title": "A", "order": 10},
                ]},
            ]},
        ],
    }
    catalog = ExploreConfigLoader(cache_ttl_seconds=0, catalog_reader=lambda: document).load()

    assert [category.id for category in catalog.categories] == ["first", "second"]
    assert [topic.id for topic in catalog.categories[0].topics] == ["watch"]
    assert [item.id for item in catalog.categories[0].topics[0].items] == ["a-item", "z-item"]


def test_database_failure_keeps_last_good_catalog():
    document = {"version": 1, "categories": [{"id": "french", "title": "French"}]}
    loader = ExploreConfigLoader(cache_ttl_seconds=0, catalog_reader=lambda: document)
    assert loader.load().categories[0].id == "french"

    def fail():
        raise ConnectionError("database unavailable")

    loader.catalog_reader = fail
    assert loader.load().categories[0].id == "french"


def test_invalid_document_does_not_replace_last_good_catalog():
    document = {"version": 1, "categories": [{"id": "english", "title": "English"}]}
    loader = ExploreConfigLoader(cache_ttl_seconds=0, catalog_reader=lambda: document)
    assert loader.load().categories[0].id == "english"
    loader.catalog_reader = lambda: {"categories": [{"id": "broken"}]}
    assert loader.load().categories[0].id == "english"


def test_missing_database_catalog_returns_empty_view():
    loader = ExploreConfigLoader(cache_ttl_seconds=0, catalog_reader=lambda: None)
    assert loader.load().categories == []
