from services.content_tags import normalize_content_tags
from services.explore_config import ExploreCatalog
from repositories.explore_repo import _add_explore_item


def test_canonical_topics_ignore_unknown_values_and_do_not_duplicate_aliases():
    assert normalize_content_tags([" Actualité ", "news", "Science", "sports", "<script>", 1]) == ["news", "science", "sport"]
    assert normalize_content_tags("news") == []
    assert normalize_content_tags(["fr", "B2", "video"]) == []


def test_legacy_catalogs_and_new_shares_carry_the_same_topics():
    document = {"categories": [{"id": "french", "title": "French", "language": "fr", "topics": []}]}
    content = {"id": "content", "title": "Lesson", "metadata_json": {"tags": ["science", "tech"]}}
    _add_explore_item(document, content, "/youtube-watch?video_id=abcdefghijk", "abcdefghijk", "fr", None)
    item = ExploreCatalog.model_validate(document).categories[0].topics[0].items[0]
    assert item.tags == ["science", "technology"]
    del document["categories"][0]["topics"][0]["items"][0]["tags"]
    assert ExploreCatalog.model_validate(document).categories[0].topics[0].items[0].tags == []
