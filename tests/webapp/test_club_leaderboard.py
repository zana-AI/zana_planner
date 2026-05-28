from datetime import date

from webapp.routers.community import _rank_club_leaderboard_members


TODAY = date(2026, 5, 28)


def _member(user_id: str, name: str) -> dict:
    return {"user_id": user_id, "first_name": name, "username": None, "avatar_path": None}


def _count_promise(uuid: str = "p-count", target: float = 7.0) -> dict:
    return {
        "promise_uuid": uuid,
        "promise_text": "Play Cheenva",
        "metric_type": "count",
        "target_value": target,
    }


def _hours_promise(uuid: str = "p-hours", target: float = 4.0) -> dict:
    return {
        "promise_uuid": uuid,
        "promise_text": "Deep work",
        "metric_type": "hours",
        "target_value": target,
    }


def test_count_leaderboard_orders_by_rolling_active_days_then_latest_activity():
    members = [
        _member("sepideh", "Sepideh"),
        _member("javad", "Javad"),
        _member("homa", "Homa"),
        _member("marzieh", "Marzieh"),
        _member("aa", "AA"),
    ]
    promise = _count_promise()
    days = [date(2026, 5, day) for day in range(22, 29)]
    actions = {
        ("sepideh", "p-count"): {
            "active_days": set(days),
            "checkin_count": 7,
            "last_activity_at_utc": "2026-05-28T16:41:27+00:00",
        },
        ("javad", "p-count"): {
            "active_days": set(days),
            "checkin_count": 7,
            "last_activity_at_utc": "2026-05-28T00:02:01+00:00",
        },
        ("homa", "p-count"): {
            "active_days": set(days[:-1]),
            "checkin_count": 6,
            "last_activity_at_utc": "2026-05-27T21:52:44+00:00",
        },
        ("marzieh", "p-count"): {
            "active_days": {date(2026, 5, 22), date(2026, 5, 25)},
            "checkin_count": 2,
            "last_activity_at_utc": "2026-05-25T15:16:22+00:00",
        },
    }

    rows = _rank_club_leaderboard_members(
        members=members,
        promises=[promise],
        actions_by_member_promise=actions,
        today=TODAY,
        limit=10,
    )

    assert [row.first_name for row in rows] == ["Sepideh", "Javad", "Homa", "Marzieh", "AA"]
    assert [row.breakdown[0].achieved_value for row in rows] == [7, 7, 6, 2, 0]
    assert rows[0].score_percent == 100
    assert rows[1].score_percent == 100


def test_duplicate_same_day_checkins_count_as_one_active_day():
    rows = _rank_club_leaderboard_members(
        members=[_member("u1", "User")],
        promises=[_count_promise(target=7)],
        actions_by_member_promise={
            ("u1", "p-count"): {
                "active_days": {TODAY},
                "checkin_count": 2,
                "last_activity_at_utc": "2026-05-28T12:00:00+00:00",
            }
        },
        today=TODAY,
        limit=10,
    )

    assert rows[0].breakdown[0].achieved_value == 1
    assert rows[0].breakdown[0].checkin_count == 2
    assert rows[0].score_percent == 14.3


def test_log_time_does_not_count_as_binary_checkin_day():
    rows = _rank_club_leaderboard_members(
        members=[_member("u1", "User")],
        promises=[_count_promise(target=7)],
        actions_by_member_promise={
            ("u1", "p-count"): {
                "activity_days": {TODAY},
                "checkin_days": set(),
                "duration_hours": 2.0,
                "last_activity_at_utc": "2026-05-28T12:00:00+00:00",
            }
        },
        today=TODAY,
        limit=10,
    )

    assert rows[0].active_days == 1
    assert rows[0].breakdown[0].achieved_value == 0
    assert rows[0].score_percent == 0


def test_duration_promise_uses_logged_hours_over_target():
    rows = _rank_club_leaderboard_members(
        members=[_member("u1", "A"), _member("u2", "B")],
        promises=[_hours_promise(target=4)],
        actions_by_member_promise={
            ("u1", "p-hours"): {
                "active_days": {TODAY},
                "duration_hours": 3.0,
                "last_activity_at_utc": "2026-05-28T08:00:00+00:00",
            },
            ("u2", "p-hours"): {
                "active_days": {TODAY},
                "duration_hours": 1.0,
                "last_activity_at_utc": "2026-05-28T09:00:00+00:00",
            },
        },
        today=TODAY,
        limit=10,
    )

    assert [row.first_name for row in rows] == ["A", "B"]
    assert [row.score_percent for row in rows] == [75, 25]


def test_mixed_promises_average_normalized_progress():
    rows = _rank_club_leaderboard_members(
        members=[_member("u1", "Balanced"), _member("u2", "Checkins")],
        promises=[_count_promise(target=7), _hours_promise(target=4)],
        actions_by_member_promise={
            ("u1", "p-count"): {"active_days": {TODAY}, "checkin_count": 1},
            ("u1", "p-hours"): {"active_days": {TODAY}, "duration_hours": 4.0},
            ("u2", "p-count"): {
                "active_days": {date(2026, 5, day) for day in range(22, 29)},
                "checkin_count": 7,
            },
            ("u2", "p-hours"): {"active_days": set(), "duration_hours": 0.0},
        },
        today=TODAY,
        limit=10,
    )

    assert rows[0].first_name == "Balanced"
    assert rows[0].score_percent == 57.1
    assert rows[1].first_name == "Checkins"
    assert rows[1].score_percent == 50


def test_unshared_or_inactive_member_actions_are_absent_from_inputs_and_do_not_count():
    rows = _rank_club_leaderboard_members(
        members=[_member("active", "Active")],
        promises=[_count_promise()],
        actions_by_member_promise={
            ("other", "p-count"): {
                "active_days": {TODAY},
                "checkin_count": 1,
                "last_activity_at_utc": "2026-05-28T10:00:00+00:00",
            },
            ("active", "private-promise"): {
                "active_days": {TODAY},
                "checkin_count": 1,
                "last_activity_at_utc": "2026-05-28T11:00:00+00:00",
            },
        },
        today=TODAY,
        limit=10,
    )

    assert len(rows) == 1
    assert rows[0].first_name == "Active"
    assert rows[0].score_percent == 0
