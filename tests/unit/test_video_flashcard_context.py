from contextlib import contextmanager
import sys
import types


def test_learning_term_translation_uses_context_and_shared_cache(monkeypatch):
    from handlers import translator

    calls = []

    def fake_call(_api_key, system_prompt, text, **kwargs):
        calls.append((system_prompt, text, kwargs))
        return "حمایت"

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(translator, "_call_groq", fake_call)
    translator.clear_translation_cache()

    first = translator.translate_learning_term(
        "appui",
        "Les agriculteurs ont apporté leur appui.",
        target_lang="fa",
        source_lang="fr",
    )
    second = translator.translate_learning_term(
        "appui",
        "Les agriculteurs ont apporté leur appui.",
        target_lang="fa",
        source_lang="fr",
    )

    assert first == second == "حمایت"
    assert len(calls) == 1
    assert "appui" in calls[0][1]
    assert "Les agriculteurs" in calls[0][1]
    assert calls[0][2]["models"] == (translator._MODEL,)
    assert calls[0][2]["max_tokens"] == 96


def test_video_save_preserves_existing_card_and_adds_context(monkeypatch):
    fake_fsrs = types.SimpleNamespace(
        Card=object,
        Rating=object,
        Scheduler=lambda: object(),
        State=object,
    )
    monkeypatch.setitem(sys.modules, "fsrs", fake_fsrs)
    sys.modules.pop("services.flashcard_service", None)
    from services import flashcard_service

    state = {
        "note": {
            "note_id": "note-1",
            "deck_id": "deck-edito",
            "note_type": "vocab",
            "fields": {
                "front": "un appui",
                "back": "un soutien",
                "example": "Merci pour votre appui.",
            },
        },
        "updates": [],
        "references": [],
    }

    class FakeNotes:
        def get_by_source_key(self, _session, _user_id, source_key):
            assert source_key == "un appui"
            return dict(state["note"])

        def update_fields(self, _session, note_id, additions):
            assert note_id == "note-1"
            state["updates"].append(dict(additions))
            merged = dict(state["note"]["fields"])
            merged.update(additions)
            state["note"] = {**state["note"], "fields": merged}
            return dict(state["note"])

    class FakeReferences:
        def list_for_note(self, _session, _note_id):
            return list(state["references"])

        def add(self, _session, note_id, **reference):
            saved = {"reference_id": "ref-1", "note_id": note_id, **reference}
            state["references"].append(saved)
            return saved

    class MustNotCreate:
        def __getattr__(self, name):
            raise AssertionError(f"existing card must not call {name}")

    @contextmanager
    def fake_session():
        yield object()

    monkeypatch.setattr(flashcard_service, "get_db_session", fake_session)
    monkeypatch.setattr(flashcard_service, "_notes", FakeNotes())
    monkeypatch.setattr(flashcard_service, "_refs", FakeReferences())
    monkeypatch.setattr(flashcard_service, "_decks", MustNotCreate())
    monkeypatch.setattr(flashcard_service, "_cards", MustNotCreate())

    result = flashcard_service.save_context_note(
        "42",
        deck_path="French::Vidéos::Test",
        fields={
            "front": "un appui",
            "back": "حمایت",
            "example": "Les agriculteurs ont apporté leur appui.",
            "source_sentence": "Les agriculteurs ont apporté leur appui.",
            "source_url": "https://www.youtube.com/watch?v=abcdefghijk",
            "source_start": 12.5,
            "source_video_id": "abcdefghijk",
            "source_language": "fr",
        },
        references=[{
            "kind": "url",
            "locator": {"url": "https://www.youtube.com/watch?v=abcdefghijk", "start": 12.5},
            "label": "YouTube · 0:12",
        }],
    )

    assert result["_created"] is False
    assert result["deck_id"] == "deck-edito"
    assert result["fields"]["back"] == "un soutien"
    assert result["fields"]["example"] == "Merci pour votre appui."
    assert result["fields"]["source_start"] == 12.5
    assert "back" not in state["updates"][0]
    assert "example" not in state["updates"][0]
    assert len(result["references"]) == 1
