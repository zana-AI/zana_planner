from contextlib import contextmanager

from services import flashcard_service


def test_club_video_words_keep_members_cards_separate_without_review_state(monkeypatch):
    @contextmanager
    def fake_session():
        yield object()

    class FakeNotes:
        def list_for_club_video(self, session, content_id, club_id, video_id):
            assert (content_id, club_id, video_id) == ("content-1", "club-1", "video-123")
            return [
                {"note_id": "peer", "user_id": "8", "creator_name": "Marzieh", "avatar_path": None,
                 "fields": {"front": "voyager", "back": "سفر کردن", "source_video_id": video_id, "source_start": 12}},
                {"note_id": "mine", "user_id": "7", "creator_name": "Javad", "avatar_path": "public.jpg",
                 "fields": {"front": "voyager", "back": "travel", "source_video_id": video_id, "source_start": 5}},
            ]

    monkeypatch.setattr(flashcard_service, "get_db_session", fake_session)
    monkeypatch.setattr(flashcard_service, "_notes", FakeNotes())

    items = flashcard_service.list_club_video_words("content-1", "club-1", "video-123", "7")

    assert [item["note_id"] for item in items] == ["mine", "peer"]
    assert [item["is_mine"] for item in items] == [True, False]
    assert items[0]["avatar_path"] == "public.jpg"
    assert all("deck_id" not in item and "review" not in item for item in items)
