from contextlib import contextmanager

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from repositories import challenges_repo
from webapp.routers.admin import _validate_content_access
from webapp.schemas import ChallengeCreateRequest


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _ClubSession:
    def __init__(self, exists=True):
        self.exists = exists

    def execute(self, statement, params=None):
        return _ScalarResult(1 if self.exists else None)


@pytest.mark.unit
def test_club_access_requires_an_existing_club():
    with pytest.raises(HTTPException) as missing:
        _validate_content_access(_ClubSession(), "club", None)
    assert missing.value.status_code == 422

    with pytest.raises(HTTPException) as unknown:
        _validate_content_access(_ClubSession(exists=False), "club", "missing")
    assert unknown.value.status_code == 422

    assert _validate_content_access(_ClubSession(), "club", " club-1 ") == "club-1"
    assert _validate_content_access(_ClubSession(), "private", "club-1") is None


@pytest.mark.unit
def test_challenge_authoring_accepts_only_the_shared_visibility_contract():
    for visibility in ("private", "club", "public"):
        assert ChallengeCreateRequest(title="French", visibility=visibility).visibility == visibility

    with pytest.raises(ValidationError):
        ChallengeCreateRequest(title="French", visibility="unlisted")


@pytest.mark.unit
def test_join_cannot_bypass_challenge_access(monkeypatch):
    repo = challenges_repo.ChallengesRepository()
    monkeypatch.setattr(repo, "get", lambda challenge_id, user_id: None)
    called = False

    def _unexpected_subscription(*args, **kwargs):
        nonlocal called
        called = True
        return "promise"

    monkeypatch.setattr(repo, "ensure_subscription", _unexpected_subscription)
    assert repo.join("private-challenge", 42) is False
    assert called is False


@pytest.mark.unit
def test_challenge_queries_include_owner_participant_and_club_access(monkeypatch):
    captured = []

    class _Mappings:
        def fetchall(self):
            return []

        def fetchone(self):
            return None

    class _Result:
        def mappings(self):
            return _Mappings()

    class _Session:
        def execute(self, statement, params=None):
            captured.append(str(statement))
            return _Result()

    @contextmanager
    def _session():
        yield _Session()

    monkeypatch.setattr(challenges_repo, "get_db_session", _session)
    repo = challenges_repo.ChallengesRepository()
    repo.list_visible(42)
    repo.get("challenge-1", 42)

    sql = "\n".join(captured)
    assert "c.host_user_id = :user_id" in sql
    assert "challenge_participants own" in sql
    assert "club_members cm" in sql
    assert "cm.status = 'active'" in sql
