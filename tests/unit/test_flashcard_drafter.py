"""The AI draft path must never silently alter a card or mix batch rows."""

import json
import sys
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from services import flashcard_drafter, flashcard_service


def test_drafter_uses_one_structured_call_and_checks_ids(monkeypatch):
    calls = []
    rows = [
        {"id": "one", "front": "klaxonner", "back": "to honk", "example": "Il klaxonne.", "note_fa": "بوق زدن", "warning": ""},
        {"id": "two", "front": "stressé", "back": "stressed", "example": "Il est stressé.", "note_fa": "مضطرب", "warning": ""},
    ]
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"cards": rows})))])

    class Client:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            calls.append(kwargs)
            return response

    monkeypatch.setenv("GROQ_API_KEY", "fake")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=Client))
    monkeypatch.setattr(flashcard_drafter, "extract_tokens", lambda _: (10, 20))
    monkeypatch.setattr(flashcard_drafter, "record_usage_safely", lambda **_: None)
    result = flashcard_drafter.draft_cards([{"id": "one"}, {"id": "two"}])
    assert [item["fields"]["front"] for item in result] == ["klaxonner", "stressé"]
    assert len(calls) == 1
    assert calls[0]["model"] == "openai/gpt-oss-120b"
    assert calls[0]["response_format"]["json_schema"]["strict"] is True
    rows[1]["id"] = "wrong"
    response.choices[0].message.content = json.dumps({"cards": rows})
    with pytest.raises(RuntimeError, match="no changes were saved"):
        flashcard_drafter.draft_cards([{"id": "one"}, {"id": "two"}])


def test_apply_preserves_alias_and_rejects_stale_batch(monkeypatch):
    current = {
        "one": {"note_id": "one", "user_id": "7", "fields": {"front": "klaxonnent", "back": "honk", "example": "", "note_fa": ""}},
        "two": {"note_id": "two", "user_id": "7", "fields": {"front": "stressés", "back": "stressed", "example": "", "note_fa": ""}},
    }
    writes = []

    @contextmanager
    def fake_session():
        yield SimpleNamespace(execute=lambda *args, **kwargs: None)

    def update(_session, note_id, fields):
        writes.append((note_id, fields))
        current[note_id]["fields"] = {**current[note_id]["fields"], **fields}
        return current[note_id]

    monkeypatch.setattr(flashcard_service, "get_db_session", fake_session)
    monkeypatch.setattr(flashcard_service._notes, "get", lambda _session, note_id: current.get(note_id))
    monkeypatch.setattr(flashcard_service._notes, "get_by_source_key", lambda _session, _user, key: next((row for row in current.values() if row["fields"]["front"] == key), None))
    monkeypatch.setattr(flashcard_service._notes, "update_fields", update)
    first = {"note_id": "one", "expected_fields": {"front": "klaxonnent", "back": "honk", "example": "", "note_fa": ""}, "fields": {"front": "klaxonner", "back": "to honk", "example": "Il klaxonne.", "note_fa": "بوق زدن"}}
    stale = {"note_id": "two", "expected_fields": {"front": "stressés", "back": "old meaning", "example": "", "note_fa": ""}, "fields": {"front": "stressé", "back": "stressed", "example": "Il est stressé.", "note_fa": "مضطرب"}}
    with pytest.raises(ValueError, match="changed"):
        flashcard_service.apply_card_drafts("7", [first, stale])
    assert writes == []
    result = flashcard_service.apply_card_drafts("7", [first])
    assert result[0]["fields"]["_curated"] is True
    assert result[0]["fields"]["_import_aliases"] == ["klaxonnent"]
