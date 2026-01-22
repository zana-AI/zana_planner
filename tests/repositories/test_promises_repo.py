import json
import pytest
import sqlite3
from datetime import date

from models.models import Promise
from repositories.promises_repo import PromisesRepository


@pytest.mark.repo
def test_promises_repo_upsert_and_list_roundtrip(tmp_path):
    root = str(tmp_path)
    repo = PromisesRepository(root)
    user_id = 123

    p = Promise(
        user_id=str(user_id),
        id="P01",
        text="Deep_Work",
        hours_per_week=5.0,
        recurring=True,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        angle_deg=10,
        radius=2,
    )

    repo.upsert_promise(user_id, p)
    assert (tmp_path / "zana.db").exists()
    items = repo.list_promises(user_id)
    assert len(items) == 1
    assert items[0].id == "P01"
    assert items[0].text == "Deep_Work"
    assert items[0].hours_per_week == pytest.approx(5.0)


@pytest.mark.repo
def test_promises_repo_imports_legacy_json_when_csv_missing(tmp_path):
    root = str(tmp_path)
    repo = PromisesRepository(root)
    user_id = 555
    user_dir = tmp_path / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    # Create legacy JSON only; no CSV file.
    legacy = [
        {
            "id": "P01",
            "text": "Test_Promise",
            "hours_per_week": 3.5,
            "recurring": True,
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
            "angle_deg": 0,
            "radius": 0,
        }
    ]
    (user_dir / "promises.json").write_text(json.dumps(legacy), encoding="utf-8")

    items = repo.list_promises(user_id)
    assert (tmp_path / "zana.db").exists()
    assert len(items) == 1
    assert items[0].id == "P01"
    assert items[0].text == "Test_Promise"


@pytest.mark.repo
def test_promises_repo_rename_creates_alias_and_old_id_resolves(tmp_path):
    root = str(tmp_path)
    repo = PromisesRepository(root)
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

    # Check aliases table contains both P01 and P02
    db_path = tmp_path / "zana.db"
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT alias_id FROM promise_aliases WHERE user_id = ? ORDER BY alias_id ASC;",
            (str(user_id),),
        ).fetchall()
        aliases = [r[0] for r in rows]
        assert aliases == ["P01", "P02"]
    finally:
        conn.close()


@pytest.mark.repo
def test_promises_repo_writes_promise_events_for_create_rename_delete(tmp_path):
    root = str(tmp_path)
    repo = PromisesRepository(root)
    user_id = 77

    repo.upsert_promise(
        user_id,
        Promise(user_id=str(user_id), id="P01", text="X", hours_per_week=1.0, recurring=True),
    )
    p2 = Promise(user_id=str(user_id), id="P02", text="X", hours_per_week=1.0, recurring=True)
    setattr(p2, "old_id", "P01")
    repo.upsert_promise(user_id, p2)
    assert repo.delete_promise(user_id, "P02") is True

    db_path = tmp_path / "zana.db"
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT event_type, snapshot_json FROM promise_events WHERE user_id = ? ORDER BY at_utc ASC;",
            (str(user_id),),
        ).fetchall()
        types = [r[0] for r in rows]
        # At least one create, one rename, and one delete
        assert "create" in types
        assert "rename" in types
        assert "delete" in types

        # Delete snapshot should mark is_deleted true
        delete_row = next((r for r in rows if r[0] == "delete"), None)
        assert delete_row is not None
        snapshot = json.loads(delete_row[1])
        assert snapshot.get("is_deleted") is True
    finally:
        conn.close()


@pytest.mark.repo
def test_promises_repo_create_subtask(tmp_path):
    """Test creating a subtask with a parent promise."""
    root = str(tmp_path)
    repo = PromisesRepository(root)
    user_id = 100

    # Create parent promise
    parent = Promise(
        user_id=str(user_id),
        id="PROJECT",
        text="Big_Project",
        hours_per_week=10.0,
        recurring=True,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )
    repo.upsert_promise(user_id, parent)

    # Create subtask
    subtask = Promise(
        user_id=str(user_id),
        id="TASK01",
        text="Subtask_One",
        hours_per_week=3.0,
        recurring=True,
        parent_id="PROJECT",
    )
    repo.upsert_promise(user_id, subtask)

    # Verify subtask was created
    retrieved = repo.get_promise(user_id, "TASK01")
    assert retrieved is not None
    assert retrieved.id == "TASK01"
    assert retrieved.parent_id == "PROJECT"
    assert retrieved.text == "Subtask_One"


@pytest.mark.repo
def test_promises_repo_list_subtasks(tmp_path):
    """Test listing subtasks of a parent promise."""
    root = str(tmp_path)
    repo = PromisesRepository(root)
    user_id = 200

    # Create parent
    parent = Promise(
        user_id=str(user_id),
        id="PROJ",
        text="Project",
        hours_per_week=10.0,
        recurring=True,
    )
    repo.upsert_promise(user_id, parent)

    # Create multiple subtasks
    for i in range(1, 4):
        subtask = Promise(
            user_id=str(user_id),
            id=f"SUB{i:02d}",
            text=f"Subtask_{i}",
            hours_per_week=2.0,
            recurring=True,
            parent_id="PROJ",
        )
        repo.upsert_promise(user_id, subtask)

    # Create a top-level promise (no parent)
    top_level = Promise(
        user_id=str(user_id),
        id="TOP",
        text="Top_Level",
        hours_per_week=1.0,
        recurring=True,
    )
    repo.upsert_promise(user_id, top_level)

    # Get all subtasks of PROJ
    subtasks = repo.get_subtasks(user_id, "PROJ")
    assert len(subtasks) == 3
    assert all(s.parent_id == "PROJ" for s in subtasks)
    assert sorted([s.id for s in subtasks]) == ["SUB01", "SUB02", "SUB03"]

    # List all promises (should include parent and subtasks)
    all_promises = repo.list_promises(user_id)
    assert len(all_promises) == 5  # 1 parent + 3 subtasks + 1 top-level


@pytest.mark.repo
def test_promises_repo_has_subtasks(tmp_path):
    """Test checking if a promise has subtasks."""
    root = str(tmp_path)
    repo = PromisesRepository(root)
    user_id = 300

    # Create parent without subtasks initially
    parent = Promise(
        user_id=str(user_id),
        id="PARENT",
        text="Parent_Promise",
        hours_per_week=5.0,
        recurring=True,
    )
    repo.upsert_promise(user_id, parent)

    # Should not have subtasks yet
    assert not repo.has_subtasks(user_id, "PARENT")

    # Create a subtask
    subtask = Promise(
        user_id=str(user_id),
        id="CHILD",
        text="Child_Promise",
        hours_per_week=2.0,
        recurring=True,
        parent_id="PARENT",
    )
    repo.upsert_promise(user_id, subtask)

    # Should now have subtasks
    assert repo.has_subtasks(user_id, "PARENT")


@pytest.mark.repo
def test_promises_repo_nested_subtasks(tmp_path):
    """Test creating nested hierarchies of subtasks."""
    root = str(tmp_path)
    repo = PromisesRepository(root)
    user_id = 400

    # Create three-level hierarchy: PROJECT -> PHASE -> TASK
    project = Promise(
        user_id=str(user_id),
        id="PROJECT",
        text="Main_Project",
        hours_per_week=20.0,
        recurring=True,
    )
    repo.upsert_promise(user_id, project)

    phase = Promise(
        user_id=str(user_id),
        id="PHASE1",
        text="Phase_One",
        hours_per_week=10.0,
        recurring=True,
        parent_id="PROJECT",
    )
    repo.upsert_promise(user_id, phase)

    task = Promise(
        user_id=str(user_id),
        id="TASK1",
        text="Task_One",
        hours_per_week=5.0,
        recurring=True,
        parent_id="PHASE1",
    )
    repo.upsert_promise(user_id, task)

    # Verify hierarchy
    retrieved_task = repo.get_promise(user_id, "TASK1")
    assert retrieved_task.parent_id == "PHASE1"

    retrieved_phase = repo.get_promise(user_id, "PHASE1")
    assert retrieved_phase.parent_id == "PROJECT"

    retrieved_project = repo.get_promise(user_id, "PROJECT")
    assert retrieved_project.parent_id is None

    # Check subtasks at each level
    project_subtasks = repo.get_subtasks(user_id, "PROJECT")
    assert len(project_subtasks) == 1
    assert project_subtasks[0].id == "PHASE1"

    phase_subtasks = repo.get_subtasks(user_id, "PHASE1")
    assert len(phase_subtasks) == 1
    assert phase_subtasks[0].id == "TASK1"

    task_subtasks = repo.get_subtasks(user_id, "TASK1")
    assert len(task_subtasks) == 0


@pytest.mark.repo
def test_promises_repo_update_subtask_parent(tmp_path):
    """Test updating a subtask to change its parent."""
    root = str(tmp_path)
    repo = PromisesRepository(root)
    user_id = 500

    # Create two parent promises
    parent1 = Promise(
        user_id=str(user_id),
        id="PARENT1",
        text="First_Parent",
        hours_per_week=5.0,
        recurring=True,
    )
    repo.upsert_promise(user_id, parent1)

    parent2 = Promise(
        user_id=str(user_id),
        id="PARENT2",
        text="Second_Parent",
        hours_per_week=5.0,
        recurring=True,
    )
    repo.upsert_promise(user_id, parent2)

    # Create subtask under parent1
    subtask = Promise(
        user_id=str(user_id),
        id="SUBTASK",
        text="Mobile_Subtask",
        hours_per_week=2.0,
        recurring=True,
        parent_id="PARENT1",
    )
    repo.upsert_promise(user_id, subtask)

    # Verify initial parent
    assert repo.get_subtasks(user_id, "PARENT1")[0].id == "SUBTASK"
    assert len(repo.get_subtasks(user_id, "PARENT2")) == 0

    # Move subtask to parent2
    subtask.parent_id = "PARENT2"
    repo.upsert_promise(user_id, subtask)

    # Verify new parent
    assert len(repo.get_subtasks(user_id, "PARENT1")) == 0
    assert repo.get_subtasks(user_id, "PARENT2")[0].id == "SUBTASK"
