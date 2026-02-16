import pytest

from services.planner_api_adapter import PlannerAPIAdapter


@pytest.mark.integration
def test_planner_api_adapter_add_promise_persists(tmp_path):
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_id = 123

    msg = adapter.add_promise(user_id, promise_text="Test Promise", num_hours_promised_per_week=5.0, recurring=True)
    assert "added successfully" in msg

    promises = adapter.get_promises(user_id)
    assert len(promises) == 1
    assert promises[0]["text"] == "Test_Promise"


@pytest.mark.integration
def test_planner_api_adapter_add_action_and_weekly_progress(tmp_path):
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_id = 123

    msg = adapter.add_promise(user_id, promise_text="Weekly Progress", num_hours_promised_per_week=10.0)
    promise_id = msg.split()[0].lstrip("#")

    out = adapter.add_action(user_id, promise_id, 5.0)
    assert "Action logged" in out

    progress = adapter.get_promise_weekly_progress(user_id, promise_id)
    assert progress == pytest.approx(0.5, abs=0.05)


@pytest.mark.integration
def test_planner_api_adapter_weekly_report_mentions_promise(tmp_path):
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_id = 123
    msg = adapter.add_promise(user_id, promise_text="Report Test", num_hours_promised_per_week=8.0)
    promise_id = msg.split()[0].lstrip("#")
    adapter.add_action(user_id, promise_id, 1.0)

    report = adapter.get_weekly_report(user_id)
    assert f"#{promise_id}" in report
    assert "Report Test" in report


# Tests for new query methods

@pytest.mark.integration
def test_search_promises_finds_by_text(tmp_path):
    """Test that search_promises finds promises by keyword."""
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_id = 123
    
    # Create multiple promises
    adapter.add_promise(user_id, promise_text="Go to gym", num_hours_promised_per_week=3.0)
    adapter.add_promise(user_id, promise_text="Study math", num_hours_promised_per_week=5.0)
    adapter.add_promise(user_id, promise_text="Read books", num_hours_promised_per_week=2.0)
    
    # Search for "gym"
    result = adapter.search_promises(user_id, "gym")
    assert "gym" in result.lower()
    assert "Found 1 promise" in result
    assert "math" not in result.lower()


@pytest.mark.integration
def test_search_promises_case_insensitive(tmp_path):
    """Test that search is case-insensitive."""
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_id = 123
    
    adapter.add_promise(user_id, promise_text="Do Sport", num_hours_promised_per_week=3.0)
    
    # Search with different cases
    result_lower = adapter.search_promises(user_id, "sport")
    result_upper = adapter.search_promises(user_id, "SPORT")
    result_mixed = adapter.search_promises(user_id, "SpOrT")
    
    assert "Found 1 promise" in result_lower
    assert "Found 1 promise" in result_upper
    assert "Found 1 promise" in result_mixed


@pytest.mark.integration
def test_search_promises_no_results(tmp_path):
    """Test search returns appropriate message when no matches."""
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_id = 123
    
    adapter.add_promise(user_id, promise_text="Study Python", num_hours_promised_per_week=5.0)
    
    result = adapter.search_promises(user_id, "cooking")
    assert "No promises found" in result


@pytest.mark.integration
def test_get_hours_for_promise_with_date_range(tmp_path):
    """Test get_promise_hours_total with date filtering."""
    from datetime import datetime, timedelta
    
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_id = 123
    
    msg = adapter.add_promise(user_id, promise_text="Exercise", num_hours_promised_per_week=5.0)
    promise_id = msg.split()[0].lstrip("#")
    
    # Add actions at different times
    now = datetime.now()
    adapter.add_action(user_id, promise_id, 2.0, action_datetime=now)
    adapter.add_action(user_id, promise_id, 1.5, action_datetime=now - timedelta(days=1))
    adapter.add_action(user_id, promise_id, 3.0, action_datetime=now - timedelta(days=10))
    
    # Get hours for all time
    result_all = adapter.get_promise_hours_total(user_id, promise_id)
    assert "6.5 hours" in result_all
    
    # Get hours since 5 days ago (should exclude the 10-day-old action)
    since_date = (now - timedelta(days=5)).strftime("%Y-%m-%d")
    result_filtered = adapter.get_promise_hours_total(user_id, promise_id, since_date=since_date)
    assert "3.5 hours" in result_filtered


@pytest.mark.integration
def test_get_hours_for_promise_all_time(tmp_path):
    """Test get_promise_hours_total without date filter returns all hours."""
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_id = 123
    
    msg = adapter.add_promise(user_id, promise_text="Meditation", num_hours_promised_per_week=1.0)
    promise_id = msg.split()[0].lstrip("#")
    
    adapter.add_action(user_id, promise_id, 0.5)
    adapter.add_action(user_id, promise_id, 0.75)
    adapter.add_action(user_id, promise_id, 0.25)
    
    result = adapter.get_promise_hours_total(user_id, promise_id)
    assert "1.5 hours" in result
    assert "3" in result  # 3 sessions


@pytest.mark.integration
def test_get_total_hours_aggregates_all(tmp_path):
    """Test get_all_hours_total aggregates across all promises."""
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_id = 123
    
    # Create two promises with actions
    msg1 = adapter.add_promise(user_id, promise_text="Coding", num_hours_promised_per_week=10.0)
    pid1 = msg1.split()[0].lstrip("#")
    
    msg2 = adapter.add_promise(user_id, promise_text="Reading", num_hours_promised_per_week=5.0)
    pid2 = msg2.split()[0].lstrip("#")
    
    adapter.add_action(user_id, pid1, 4.0)
    adapter.add_action(user_id, pid1, 2.0)
    adapter.add_action(user_id, pid2, 1.5)
    
    result = adapter.get_all_hours_total(user_id)
    assert "7.5 hours" in result
    assert "Coding" in result
    assert "Reading" in result
    assert f"#{pid1}" in result
    assert f"#{pid2}" in result


@pytest.mark.integration
def test_get_total_hours_respects_date_range(tmp_path):
    """Test get_all_hours_total filters by date range."""
    from datetime import datetime, timedelta
    
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_id = 123
    
    msg = adapter.add_promise(user_id, promise_text="Writing", num_hours_promised_per_week=3.0)
    promise_id = msg.split()[0].lstrip("#")
    
    now = datetime.now()
    adapter.add_action(user_id, promise_id, 1.0, action_datetime=now)
    adapter.add_action(user_id, promise_id, 2.0, action_datetime=now - timedelta(days=30))
    
    # Get hours since 10 days ago (should only include recent action)
    since_date = (now - timedelta(days=10)).strftime("%Y-%m-%d")
    result = adapter.get_all_hours_total(user_id, since_date=since_date)
    assert "1.0 hours" in result


@pytest.mark.integration
def test_get_actions_in_range_filters_correctly(tmp_path):
    """Test list_actions_filtered with combined filters."""
    from datetime import datetime, timedelta
    
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_id = 123
    
    # Create two promises
    msg1 = adapter.add_promise(user_id, promise_text="Project A", num_hours_promised_per_week=10.0)
    pid1 = msg1.split()[0].lstrip("#")
    
    msg2 = adapter.add_promise(user_id, promise_text="Project B", num_hours_promised_per_week=5.0)
    pid2 = msg2.split()[0].lstrip("#")
    
    now = datetime.now()
    adapter.add_action(user_id, pid1, 2.0, action_datetime=now)
    adapter.add_action(user_id, pid1, 1.0, action_datetime=now - timedelta(days=5))
    adapter.add_action(user_id, pid2, 3.0, action_datetime=now - timedelta(days=2))
    
    # Filter by promise only
    result_promise = adapter.list_actions_filtered(user_id, promise_id=pid1)
    assert f"#{pid1}" in result_promise
    assert "3.0 hours" in result_promise  # 2.0 + 1.0
    assert "2 session" in result_promise
    
    # Filter by date only (last 3 days)
    since_date = (now - timedelta(days=3)).strftime("%Y-%m-%d")
    result_date = adapter.list_actions_filtered(user_id, since_date=since_date)
    assert "5.0 hours" in result_date  # 2.0 + 3.0 (excludes 5-day-old action)
    
    # Combined filter
    result_both = adapter.list_actions_filtered(user_id, promise_id=pid1, since_date=since_date)
    assert "2.0 hours" in result_both  # Only the recent pid1 action


# Security tests for SQL query feature

@pytest.mark.integration
def test_query_database_select_allowed(tmp_path):
    """Test that valid SELECT queries work."""
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_id = 123
    
    # Create some data first
    msg = adapter.add_promise(user_id, promise_text="Test Query", num_hours_promised_per_week=5.0)
    promise_id = msg.split()[0].lstrip("#")
    adapter.add_action(user_id, promise_id, 2.0)
    
    # Query with proper user_id filter
    result = adapter.query_database(
        user_id, 
        f"SELECT promise_id_text, SUM(time_spent_hours) as hours FROM actions WHERE user_id = '{user_id}' GROUP BY promise_id_text"
    )
    
    assert "Query returned" in result
    assert "2.0" in result or "2.00" in result


@pytest.mark.integration
def test_query_database_blocks_insert(tmp_path):
    """Test that INSERT statements are rejected."""
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_id = 123
    
    result = adapter.query_database(
        user_id,
        f"INSERT INTO actions (user_id, time_spent_hours) VALUES ('{user_id}', 100)"
    )
    
    assert "rejected" in result.lower() or "only select" in result.lower()


@pytest.mark.integration
def test_query_database_blocks_update(tmp_path):
    """Test that UPDATE statements are rejected."""
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_id = 123
    
    result = adapter.query_database(
        user_id,
        f"UPDATE actions SET time_spent_hours = 100 WHERE user_id = '{user_id}'"
    )
    
    assert "rejected" in result.lower() or "only select" in result.lower()


@pytest.mark.integration
def test_query_database_blocks_delete(tmp_path):
    """Test that DELETE statements are rejected."""
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_id = 123
    
    result = adapter.query_database(
        user_id,
        f"DELETE FROM actions WHERE user_id = '{user_id}'"
    )
    
    assert "rejected" in result.lower() or "only select" in result.lower()


@pytest.mark.integration
def test_query_database_blocks_drop(tmp_path):
    """Test that DROP statements are rejected."""
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_id = 123
    
    result = adapter.query_database(
        user_id,
        "DROP TABLE actions"
    )
    
    assert "rejected" in result.lower() or "only select" in result.lower()


@pytest.mark.integration
def test_query_database_enforces_user_id(tmp_path):
    """Test that queries for other users are rejected."""
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_id = 123
    other_user_id = 999
    
    # Create data for user 123
    msg = adapter.add_promise(user_id, promise_text="My Promise", num_hours_promised_per_week=5.0)
    promise_id = msg.split()[0].lstrip("#")
    adapter.add_action(user_id, promise_id, 2.0)
    
    # Try to query as user 123 but with a filter for user 999
    result = adapter.query_database(
        user_id,
        f"SELECT * FROM actions WHERE user_id = '{other_user_id}'"
    )
    
    # Should be rejected because user_id in query doesn't match
    assert "rejected" in result.lower() or "your own data" in result.lower()


@pytest.mark.integration
def test_query_database_requires_user_id_filter(tmp_path):
    """Test that queries without user_id filter are rejected."""
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_id = 123
    
    # Query without user_id filter
    result = adapter.query_database(
        user_id,
        "SELECT * FROM actions"
    )
    
    # Should be rejected for missing user_id filter
    assert "rejected" in result.lower() or "user_id" in result.lower()


@pytest.mark.integration
def test_query_database_limits_results(tmp_path):
    """Test that results are capped at 100 rows."""
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_id = 123
    
    # Create a promise
    msg = adapter.add_promise(user_id, promise_text="Many Actions", num_hours_promised_per_week=100.0)
    promise_id = msg.split()[0].lstrip("#")
    
    # Add many actions (more than 100)
    from datetime import datetime, timedelta
    now = datetime.now()
    for i in range(150):
        adapter.add_action(user_id, promise_id, 0.1, action_datetime=now - timedelta(hours=i))
    
    # Query should return but be limited
    result = adapter.query_database(
        user_id,
        f"SELECT * FROM actions WHERE user_id = '{user_id}'"
    )
    
    # Should have results but be limited
    assert "Query returned" in result
    # Count actual result rows (lines starting with "[")
    result_lines = [l for l in result.split("\n") if l.strip().startswith("[")]
    assert len(result_lines) <= 100


@pytest.mark.integration
def test_query_database_handles_syntax_error(tmp_path):
    """Test that SQL syntax errors are handled gracefully."""
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_id = 123
    
    # Query with syntax error
    result = adapter.query_database(
        user_id,
        f"SELECT * FORM actions WHERE user_id = '{user_id}'"  # FORM instead of FROM
    )
    
    # Should return error but not crash
    assert "syntax" in result.lower() or "failed" in result.lower() or "error" in result.lower()