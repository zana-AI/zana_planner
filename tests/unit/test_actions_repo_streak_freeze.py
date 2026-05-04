from datetime import date

from repositories import actions_repo
from repositories.actions_repo import ActionsRepository


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, *_args, **_kwargs):
        return _FakeResult(self.rows)


class _FakeDbContext:
    def __init__(self, rows):
        self.session = _FakeSession(rows)

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        return False


def _streak(monkeypatch, check_dates, reference=date(2026, 5, 10)):
    rows = [(check_date,) for check_date in check_dates]
    monkeypatch.setattr(actions_repo, "get_db_session", lambda: _FakeDbContext(rows))
    return ActionsRepository().get_checkin_streak(1, "promise-uuid", reference_date=reference)


def test_streak_counts_consecutive_days(monkeypatch):
    assert _streak(monkeypatch, [date(2026, 5, 10), date(2026, 5, 9), date(2026, 5, 8)]) == 3


def test_streak_bridges_one_missed_day(monkeypatch):
    assert _streak(monkeypatch, [date(2026, 5, 10), date(2026, 5, 8), date(2026, 5, 7)]) == 3


def test_streak_bridges_two_missed_days(monkeypatch):
    assert _streak(monkeypatch, [date(2026, 5, 10), date(2026, 5, 7), date(2026, 5, 6)]) == 3


def test_streak_breaks_after_three_missed_days(monkeypatch):
    assert _streak(monkeypatch, [date(2026, 5, 6), date(2026, 5, 5)]) == 0


def test_today_checkin_does_not_double_count(monkeypatch):
    assert _streak(monkeypatch, [date(2026, 5, 10), date(2026, 5, 9)]) == 2
