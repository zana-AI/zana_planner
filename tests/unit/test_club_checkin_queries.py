from repositories import clubs_repo
from repositories.clubs_repo import ClubsRepository


class _FakeResult:
    def mappings(self):
        return self

    def fetchall(self):
        return []


class _FakeSession:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), dict(params or {})))
        return _FakeResult()


class _FakeDbContext:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        return False


def test_recent_checkins_query_is_strictly_club_scoped(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(clubs_repo, "get_db_session", lambda: _FakeDbContext(session))

    rows = ClubsRepository().get_recent_checkins("club-1", days=99, limit=999)

    assert rows == []
    sql, params = session.calls[0]
    assert params["club_id"] == "club-1"
    assert params["limit"] == 300
    assert "cm.status = 'active'" in sql
    assert "pcs.club_id = cm.club_id" in sql
    assert "a.user_id = cm.user_id" in sql
    assert "a.promise_uuid = pcs.promise_uuid" in sql
    assert "a.action_type = 'club_checkin'" in sql


def test_today_club_checkins_query_is_strictly_club_scoped(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(clubs_repo, "get_db_session", lambda: _FakeDbContext(session))

    checked_in = ClubsRepository().get_today_club_checkins("club-2")

    assert checked_in == set()
    sql, params = session.calls[0]
    assert params["club_id"] == "club-2"
    assert "cm.status = 'active'" in sql
    assert "pcs.club_id = cm.club_id" in sql
    assert "a.user_id = cm.user_id" in sql
    assert "a.promise_uuid = pcs.promise_uuid" in sql
    assert "a.action_type = 'club_checkin'" in sql
