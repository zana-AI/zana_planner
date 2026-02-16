import pytest
from datetime import datetime

from models.models import Action
from repositories.actions_repo import ActionsRepository


@pytest.mark.repo
def test_actions_repo_append_and_list_roundtrip(tmp_path):
    repo = ActionsRepository()
    user_id = 100

    a = Action(
        user_id=user_id,
        promise_id="P01",
        action="log_time",
        time_spent=0.5,
        at=datetime(2025, 1, 19, 21, 33),
    )
    repo.append_action(a)

    items = repo.list_actions(user_id)
    assert len(items) == 1
    assert items[0].promise_id == "P01"
    assert items[0].time_spent == pytest.approx(0.5)
