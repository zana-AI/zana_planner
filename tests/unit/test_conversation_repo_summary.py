from repositories.conversation_repo import ConversationRepository


def test_extract_session_time_tag_from_time_tagged_session_id():
    session_id = "s-20260110T120000Z-abcdef12"
    assert ConversationRepository._extract_session_time_tag_utc(session_id) == "2026-01-10T12:00:00Z"


def test_recent_summary_is_chronological_and_session_aware(monkeypatch):
    repo = ConversationRepository()
    # Repository returns DESC order; summary must reconstruct chronological exchanges.
    # Include optional importance fields (migration 010) so summary path accepts them.
    history_desc = [
        {
            "id": 6,
            "message_type": "bot",
            "content": "B2",
            "created_at_utc": "2026-01-10T12:03:00Z",
            "conversation_session_id": "s-20260110T120000Z-22222222",
            "created_at": None,
            "importance_score": 60,
            "intent_category": "clarification",
        },
        {
            "id": 5,
            "message_type": "user",
            "content": "U2",
            "created_at_utc": "2026-01-10T12:02:00Z",
            "conversation_session_id": "s-20260110T120000Z-22222222",
            "created_at": None,
            "importance_score": None,
            "intent_category": None,
        },
        {
            "id": 4,
            "message_type": "bot",
            "content": "B1",
            "created_at_utc": "2026-01-10T12:01:00Z",
            "conversation_session_id": "s-20260110T120000Z-22222222",
            "created_at": None,
            "importance_score": 70,
            "intent_category": "coaching_question",
        },
        {
            "id": 3,
            "message_type": "user",
            "content": "U1",
            "created_at_utc": "2026-01-10T12:00:00Z",
            "conversation_session_id": "s-20260110T120000Z-22222222",
            "created_at": None,
            "importance_score": 80,
            "intent_category": "promise_creation",
            "importance_reasoning": "User stated a goal",
            "key_themes": ["goal"],
            "scored_at_utc": "2026-01-10T12:00:01Z",
        },
        {
            "id": 2,
            "message_type": "bot",
            "content": "old-bot",
            "created_at_utc": "2026-01-10T09:01:00Z",
            "conversation_session_id": "s-20260110T090000Z-11111111",
            "created_at": None,
        },
        {
            "id": 1,
            "message_type": "user",
            "content": "old-user",
            "created_at_utc": "2026-01-10T09:00:00Z",
            "conversation_session_id": "s-20260110T090000Z-11111111",
            "created_at": None,
        },
    ]
    monkeypatch.setattr(repo, "get_recent_history", lambda user_id, limit=50: history_desc)

    summary = repo.get_recent_conversation_summary(user_id=1, limit=2)

    assert "[Session 2026-01-10 12:00 UTC]" in summary
    assert "old-user" not in summary
    assert summary.find("User: U1") < summary.find("Bot: B1")
    assert summary.find("Bot: B1") < summary.find("User: U2")
    assert summary.find("User: U2") < summary.find("Bot: B2")
    # Importance fields (migration 010) may be present in history; summary should still work
    assert any("importance_score" in m for m in history_desc)
    assert history_desc[3].get("intent_category") == "promise_creation"

