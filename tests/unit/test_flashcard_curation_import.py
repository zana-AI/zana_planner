"""A source reimport must reuse a curated card and keep its review identity."""

from unittest.mock import MagicMock

from tm_bot.repositories.flashcard_repo import FlashcardNoteRepository


def test_reimport_of_old_inflected_prompt_preserves_curated_note():
    repo = FlashcardNoteRepository()
    session = MagicMock()
    existing = {
        "note_id": "known-card",
        "fields": {
            "front": "klaxonner",
            "back": "بوق زدن",
            "original_front": "klaxonnent",
            "_import_aliases": ["klaxonnent"],
            "_curated": True,
        },
    }
    repo.get_by_source_key = MagicMock(return_value=existing)

    result = repo.upsert(
        session,
        user_id="learner",
        deck_id="video-deck",
        fields={"front": "klaxonnent", "back": "old imported definition"},
        source="video",
    )

    repo.get_by_source_key.assert_called_once_with(session, "learner", "klaxonnent")
    session.execute.assert_not_called()
    assert result["note_id"] == "known-card"
    assert result["fields"]["front"] == "klaxonner"
    assert result["fields"]["back"] == "بوق زدن"
    assert result["_created"] is False
