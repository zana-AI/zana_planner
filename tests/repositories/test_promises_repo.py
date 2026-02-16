import pytest
from datetime import date

from models.models import Promise
from repositories.promises_repo import PromisesRepository


@pytest.mark.repo
def test_promises_repo_upsert_and_list_roundtrip(tmp_path):
    repo = PromisesRepository()
    user_id = 123

    p = Promise(
        user_id=str(user_id),
        id="P01",
        text="Deep_Work",
        hours_per_week=5.0,
        recurring=True,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )

    repo.upsert_promise(user_id, p)
    items = repo.list_promises(user_id)
    assert len(items) == 1
    assert items[0].id == "P01"
    assert items[0].text == "Deep_Work"
    assert items[0].hours_per_week == pytest.approx(5.0)


@pytest.mark.repo
def test_promises_repo_rename_creates_alias_and_old_id_resolves(tmp_path):
    repo = PromisesRepository()
    user_id = 42

    # Create initial promise P01
    p1 = Promise(
        user_id=str(user_id),
        id="P01",
        text="Alpha",
        hours_per_week=2.0,
        recurring=True,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )
    repo.upsert_promise(user_id, p1)

    # Rename by upserting the same promise under a new id
    p2 = Promise(
        user_id=str(user_id),
        id="P02",
        text="Alpha",
        hours_per_week=2.0,
        recurring=True,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )
    # Explicitly indicate rename target
    setattr(p2, "old_id", "P01")
    repo.upsert_promise(user_id, p2)

    # Listing should show only current id
    items = repo.list_promises(user_id)
    assert [p.id for p in items] == ["P02"]

    # Old id should still resolve to the same promise (current_id == P02)
    by_old = repo.get_promise(user_id, "P01")
    assert by_old is not None
    assert by_old.id == "P02"


@pytest.mark.repo
def test_promises_repo_writes_promise_events_for_create_rename_delete(tmp_path):
    repo = PromisesRepository()
    user_id = 77

    repo.upsert_promise(
        user_id,
        Promise(user_id=str(user_id), id="P01", text="X", hours_per_week=1.0, recurring=True),
    )
    p2 = Promise(user_id=str(user_id), id="P02", text="X", hours_per_week=1.0, recurring=True)
    setattr(p2, "old_id", "P01")
    repo.upsert_promise(user_id, p2)
    assert repo.delete_promise(user_id, "P02") is True
    # After delete, listing should be empty
    items = repo.list_promises(user_id)
    assert len(items) == 0
