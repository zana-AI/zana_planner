"""Actions repository tests (PostgreSQL). Requires DB at schema head: run `python scripts/run_migrations.py` with DATABASE_URL_STAGING set."""
import pytest
from datetime import datetime

from models.models import Action
from repositories.actions_repo import ActionsRepository

from tests.test_config import unique_user_id


@pytest.mark.repo
@pytest.mark.requires_postgres
def test_actions_repo_append_and_list_roundtrip(tmp_path):
    """Append one action and assert list roundtrip. Uses unique_user_id for isolation (ActionsRepository has no delete_action)."""
    repo = ActionsRepository()
    user_id = unique_user_id()

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
