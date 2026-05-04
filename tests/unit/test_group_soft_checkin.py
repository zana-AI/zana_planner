from types import SimpleNamespace

import planner_bot as planner_bot_mod
from planner_bot import PlannerBot
from repositories import actions_repo as actions_repo_mod
from router_types import InputContext


class _FakeClubsRepository:
    def get_club_members_promises(self, club_id):
        assert club_id == "club-1"
        return [{
            "user_id": "42",
            "first_name": "Javad",
            "username": "javad",
            "latin_name": "Javad",
            "non_latin_name": "\u062c\u0648\u0627\u062f",
            "promise_uuid": "promise-1",
            "promise_text": "Daily practice",
        }]

    def get_today_club_checkins(self, club_id):
        assert club_id == "club-1"
        return set()


class _FakeActionsRepository:
    recorded = []

    def append_club_checkin(self, user_id, promise_uuid, notes=None):
        self.recorded.append((user_id, promise_uuid, notes))

    def get_today_checkins(self, promise_uuid):
        assert promise_uuid == "promise-1"
        return {"42"}

    def get_checkin_streak(self, user_id, promise_uuid):
        assert user_id == 42
        assert promise_uuid == "promise-1"
        return 4


class _FakeBot:
    def __init__(self):
        self.edits = []

    async def edit_message_text(self, **kwargs):
        self.edits.append(kwargs)


async def test_group_activity_evidence_records_checkin_and_refreshes_card(monkeypatch):
    _FakeActionsRepository.recorded = []
    monkeypatch.setattr(planner_bot_mod, "ClubsRepository", lambda: _FakeClubsRepository())
    monkeypatch.setattr(actions_repo_mod, "ActionsRepository", _FakeActionsRepository)

    bot = object.__new__(PlannerBot)
    fake_bot = _FakeBot()
    bot_data = {
        "club_checkins": {
            (-100, 55): {
                "club_id": "club-1",
                "club_name": "Club",
                "promise_text": "Daily practice",
                "promise_uuid": "promise-1",
                "members": [{"user_id": 42, "name": "Javad", "status": None, "streak": 3}],
            }
        }
    }
    ctx = InputContext(
        user_id=42,
        chat_id=-100,
        input_type="text",
        raw_text="I played today\nscore 5/6\n00:04:26",
        platform_context=SimpleNamespace(bot=fake_bot),
    )
    club = {
        "club_id": "club-1",
        "club_name": "Club",
        "owner_user_id": "",
        "club_language": "en",
        "club_checkin_what_counts": "daily practice",
        "promise_text": "Daily practice",
    }

    recorded = await bot._maybe_record_group_activity_checkin(ctx, club, bot_data)

    assert recorded is True
    assert _FakeActionsRepository.recorded
    user_id, promise_uuid, notes = _FakeActionsRepository.recorded[0]
    assert (user_id, promise_uuid) == (42, "promise-1")
    assert notes.startswith("source=group_activity_evidence;reason=")
    assert "completion_phrase" in notes
    member = bot_data["club_checkins"][(-100, 55)]["members"][0]
    assert member["status"] == "done"
    assert member["streak"] == 4
    assert fake_bot.edits
    assert "\u2705 Javad \U0001f5254" in fake_bot.edits[0]["text"]
