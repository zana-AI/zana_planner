"""Stable public-content topics, also usable for future learner interests."""
import unicodedata

CONTENT_TAGS = (
    "news", "science", "sport", "technology", "culture", "economy",
    "politics", "society", "health", "travel", "nature", "food", "language_learning",
)
_ALIASES = {"actualite": "news", "actualites": "news", "actualité": "news", "actualités": "news",
            "sports": "sport", "tech": "technology", "economics": "economy"}


def normalize_content_tags(value: object) -> list[str]:
    """Ignore unsupported labels; never derive topics from language or level."""
    if not isinstance(value, (list, tuple)):
        return []
    result = []
    for raw in value:
        if not isinstance(raw, str):
            continue
        label = unicodedata.normalize("NFKC", raw).strip().lower()
        label = _ALIASES.get(label, label)
        if label in CONTENT_TAGS and label not in result:
            result.append(label)
    return result[:3]
