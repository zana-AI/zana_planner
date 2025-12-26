import pytest
from datetime import date

from repositories.nightly_state_repo import NightlyStateRepository


@pytest.mark.repo
def test_nightly_state_tracks_shown_ids_per_day(tmp_path):
    repo = NightlyStateRepository(str(tmp_path))
    user_id = 1
    d1 = date(2025, 1, 1)
    d2 = date(2025, 1, 2)

    assert repo.get_shown_promise_ids(user_id, d1) == set()

    repo.mark_promises_as_shown(user_id, ["P01", "P02"], d1)
    assert repo.get_shown_promise_ids(user_id, d1) == {"P01", "P02"}

    # Different day should read as empty (reset semantics).
    assert repo.get_shown_promise_ids(user_id, d2) == set()

    # Reset for new day creates empty state for that day.
    repo.reset_for_new_day(user_id, d2)
    assert repo.get_shown_promise_ids(user_id, d2) == set()
