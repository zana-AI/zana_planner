import pytest

from infra.scheduler import schedule_user_daily, schedule_once, schedule_repeating


class FakeJob:
    def __init__(self):
        self.removed = False

    def schedule_removal(self):
        self.removed = True


class FakeJobQueue:
    def __init__(self):
        self.jobs_by_name = {}
        self.run_daily_calls = []
        self.run_once_calls = []
        self.run_repeating_calls = []

    def get_jobs_by_name(self, name):
        return list(self.jobs_by_name.get(name, []))

    def run_daily(self, callback, time, days, name, data):
        self.run_daily_calls.append(
            {"callback": callback, "time": time, "days": days, "name": name, "data": data}
        )

    def run_once(self, callback, when, name, data):
        self.run_once_calls.append({"callback": callback, "when": when, "name": name, "data": data})

    def run_repeating(self, callback, interval, first, name, data):
        self.run_repeating_calls.append(
            {"callback": callback, "interval": interval, "first": first, "name": name, "data": data}
        )


@pytest.mark.integration
def test_schedule_user_daily_removes_existing_jobs_and_schedules_new_one():
    jq = FakeJobQueue()
    old = FakeJob()
    jq.jobs_by_name["nightly-42"] = [old]

    def cb(_ctx):
        return None

    schedule_user_daily(jq, user_id=42, tz="UTC", callback=cb, hh=22, mm=59, name_prefix="nightly")

    assert old.removed is True
    assert len(jq.run_daily_calls) == 1
    call = jq.run_daily_calls[0]
    assert call["name"] == "nightly-42"
    assert call["data"] == {"user_id": 42}
    assert call["time"].tzinfo is not None


@pytest.mark.integration
def test_schedule_once_and_repeating_clear_existing_job_names():
    jq = FakeJobQueue()
    old_once = FakeJob()
    old_rep = FakeJob()
    jq.jobs_by_name["once-job"] = [old_once]
    jq.jobs_by_name["rep-job"] = [old_rep]

    import datetime as dt

    def cb(_ctx):
        return None

    schedule_once(jq, name="once-job", callback=cb, when_dt=dt.datetime(2030, 1, 1), data={"a": 1})
    schedule_repeating(jq, name="rep-job", callback=cb, seconds=10, data={"b": 2})

    assert old_once.removed is True
    assert old_rep.removed is True
    assert len(jq.run_once_calls) == 1
    assert len(jq.run_repeating_calls) == 1
