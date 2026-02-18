"""
Security tests: attempt to access or modify another user's data (IDOR / authorization).

These tests attack the system by passing another user's user_id at various layers
to verify that either the layer rejects the request or that the boundary is clear
(adapter trusts the caller; API must never pass client-supplied user_id).
"""

import pytest

from services.planner_api_adapter import PlannerAPIAdapter
from tests.test_config import unique_user_id, ensure_users_exist


pytestmark = [pytest.mark.integration, pytest.mark.requires_postgres]


# --- Adapter layer: passing other user_id ---
# The adapter does NOT enforce "current user" — it returns/modifies data for whichever
# user_id is passed. So if the API ever passed client-supplied user_id, it would be
# a critical vulnerability. These tests document that behavior and ensure we don't
# accidentally rely on the adapter to enforce isolation.


@pytest.mark.integration
def test_adapter_get_promises_other_user_id_returns_other_users_data_not_mine(tmp_path):
    """
    Attack: Call get_promises(other_user_id).
    Adapter returns that user's promises, not the "current" user's.
    So if an API passed request body/path user_id to the adapter, it would leak.
    """
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_a = unique_user_id()
    user_b = unique_user_id()
    ensure_users_exist(user_a, user_b)

    # User A creates a promise
    adapter.add_promise(user_a, promise_text="Secret Promise A", num_hours_promised_per_week=5.0)
    # User B has no data

    # Attack: request as "current user" A but pass user B's id — we get B's (empty) list
    promises_b = adapter.get_promises(user_b)
    assert len(promises_b) == 0

    # Request with A's id returns A's data
    promises_a = adapter.get_promises(user_a)
    assert len(promises_a) == 1
    assert "Secret Promise A" in promises_a[0]["text"] or "Secret_Promise_A" in promises_a[0]["text"]

    # So: passing other_user_id at adapter layer returns THAT user's data.
    # API must never pass client-supplied user_id; only Depends(get_current_user).


@pytest.mark.integration
def test_adapter_get_actions_other_user_id_returns_that_users_actions(tmp_path):
    """
    Attack: Call get_actions(other_user_id).
    Adapter returns that user's actions. Ensures we don't rely on adapter for isolation.
    """
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_a = unique_user_id()
    user_b = unique_user_id()
    ensure_users_exist(user_a, user_b)

    msg = adapter.add_promise(user_a, promise_text="Task", num_hours_promised_per_week=5.0)
    promise_id = msg.split()[0].lstrip("#")
    adapter.add_action(user_a, promise_id, 2.0)

    # Attack: ask for user B's actions
    actions_b = adapter.get_actions(user_b)
    assert len(actions_b) == 0

    actions_a = adapter.get_actions(user_a)
    assert len(actions_a) == 1

    # Passing user_b returns B's data (empty), not A's. API must only pass authenticated user_id.


@pytest.mark.integration
def test_adapter_get_weekly_report_other_user_id_does_not_contain_my_data(tmp_path):
    """
    Attack: Call get_weekly_report(other_user_id).
    Report is for that user. If we pass B's id we get B's (empty) report, not A's.
    """
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_a = unique_user_id()
    user_b = unique_user_id()
    ensure_users_exist(user_a, user_b)

    adapter.add_promise(user_a, promise_text="My Weekly Goal", num_hours_promised_per_week=5.0)
    report_a = adapter.get_weekly_report(user_a)
    assert "My Weekly Goal" in report_a or "My_Weekly_Goal" in report_a

    report_b = adapter.get_weekly_report(user_b)
    assert "My Weekly Goal" not in report_b and "My_Weekly_Goal" not in report_b
    # B's report is empty or minimal, not A's content.


@pytest.mark.integration
def test_adapter_add_action_other_user_id_with_my_promise_id_rejected(tmp_path):
    """
    Attack: Try to add an action for other_user_id using my promise_id.
    Adapter validates promise belongs to the same user_id → should fail.
    """
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_a = unique_user_id()
    user_b = unique_user_id()
    ensure_users_exist(user_a, user_b)

    msg = adapter.add_promise(user_a, promise_text="My Promise", num_hours_promised_per_week=5.0)
    promise_id = msg.split()[0].lstrip("#")

    # Attack: try to log an action as user B for A's promise
    result = adapter.add_action(user_b, promise_id, 1.0)
    assert "not found" in result.lower() or "Promise" in result

    # B should still have no actions; A's data unchanged
    actions_b = adapter.get_actions(user_b)
    assert len(actions_b) == 0


@pytest.mark.integration
def test_adapter_add_action_other_user_id_with_their_promise_succeeds_at_adapter_layer(tmp_path):
    """
    Attack: Add an action for other_user_id using THEIR promise_id.
    At adapter layer this succeeds — the adapter does not enforce "caller == user_id".
    This documents that the API must NEVER pass client-supplied user_id to the adapter.
    """
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_a = unique_user_id()
    user_b = unique_user_id()
    ensure_users_exist(user_a, user_b)

    # User B has a promise (we're simulating "we know B's promise_id" somehow)
    msg_b = adapter.add_promise(user_b, promise_text="B's Promise", num_hours_promised_per_week=3.0)
    promise_id_b = msg_b.split()[0].lstrip("#")

    # Attack: as caller we pass user_b and B's promise_id — adapter accepts it
    result = adapter.add_action(user_b, promise_id_b, 1.0)
    assert "Action logged" in result or "logged" in result.lower()

    # So at adapter level we can write to another user's data if we pass their user_id.
    # Security: API must only pass get_current_user to adapter, never path/body user_id.
    actions_b = adapter.get_actions(user_b)
    assert len(actions_b) == 1


# --- Query layer: try to leak another user's data via SQL ---
# query_database enforces that the query's user_id filter matches the authenticated user.
# These tests try to bypass that (different user_id in WHERE, UNION, forged user_id in SELECT).


@pytest.mark.integration
def test_query_database_rejects_select_with_other_user_id_in_where(tmp_path):
    """Attack: SELECT with WHERE user_id = other_user_id. Must be rejected."""
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_a = unique_user_id()
    other_user_id = 999
    ensure_users_exist(user_a)

    adapter.add_promise(user_a, promise_text="Private", num_hours_promised_per_week=5.0)
    result = adapter.query_database(
        user_a,
        f"SELECT * FROM actions WHERE user_id = '{other_user_id}'"
    )
    assert "rejected" in result.lower() or "own data" in result.lower()


@pytest.mark.integration
def test_query_database_rejects_union_with_other_user_data(tmp_path):
    """Attack: UNION to combine my data with another user's. Must be rejected."""
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_a = unique_user_id()
    user_b = unique_user_id()
    ensure_users_exist(user_a, user_b)

    adapter.add_promise(user_a, promise_text="Mine", num_hours_promised_per_week=5.0)
    # Try to UNION my actions with user_b's (user_b has no data, but the attempt should be rejected)
    result = adapter.query_database(
        user_a,
        f"SELECT * FROM actions WHERE user_id = '{user_a}' UNION SELECT * FROM actions WHERE user_id = '{user_b}'"
    )
    # Query service should reject due to user_id mismatch (user_b in query)
    assert "rejected" in result.lower() or "own data" in result.lower() or "not allowed" in result.lower()


@pytest.mark.integration
def test_query_database_rejects_forged_user_id_in_select(tmp_path):
    """
    Attack: SELECT forged user_id (mine) but data FROM another user.
    e.g. SELECT 'my_id' AS user_id, ... FROM actions WHERE user_id = 'other'.
    Must be rejected so we cannot bypass the wrapper filter.
    """
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_a = unique_user_id()
    user_b = unique_user_id()
    ensure_users_exist(user_a, user_b)

    adapter.add_promise(user_a, promise_text="A", num_hours_promised_per_week=5.0)
    msg_b = adapter.add_promise(user_b, promise_text="B", num_hours_promised_per_week=5.0)
    promise_id_b = msg_b.split()[0].lstrip("#")
    adapter.add_action(user_b, promise_id_b, 3.0)

    # Try to return user_b's actions but with user_id column forged to user_a
    result = adapter.query_database(
        user_a,
        f"SELECT '{user_a}' AS user_id, promise_id_text, time_spent_hours FROM actions WHERE user_id = '{user_b}'"
    )
    # Should be rejected: query contains user_id = user_b which does not match authenticated user_a
    assert "rejected" in result.lower() or "own data" in result.lower()


@pytest.mark.integration
def test_query_database_rejects_user_id_in_with_other_user(tmp_path):
    """Attack: user_id IN (my_id, other_id) to request multiple users' data. Must be rejected."""
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_a = unique_user_id()
    user_b = unique_user_id()
    ensure_users_exist(user_a, user_b)

    adapter.add_promise(user_a, promise_text="Mine", num_hours_promised_per_week=5.0)
    result = adapter.query_database(
        user_a,
        f"SELECT * FROM actions WHERE user_id IN ('{user_a}', '{user_b}')"
    )
    assert "rejected" in result.lower() or "own data" in result.lower() or "not allowed" in result.lower()
