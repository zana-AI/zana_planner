"""Tests that PlannerAPIAdapter.list_templates / get_template do not crash
when templates lack legacy fields (level, why, done, effort, target_direction).

Migration 004 removed these columns.  The adapter must use .get() with defaults.
"""
import pytest
from unittest.mock import MagicMock


def _make_adapter():
    """Construct a PlannerAPIAdapter with mocked dependencies, bypassing __init__."""
    from services.planner_api_adapter import PlannerAPIAdapter

    adapter = object.__new__(PlannerAPIAdapter)
    adapter.templates_repo = MagicMock()
    adapter.unlocks_service = MagicMock()
    adapter.promises_repo = MagicMock()
    adapter.actions_repo = MagicMock()
    adapter.instances_repo = MagicMock()
    adapter.settings_repo = MagicMock()
    adapter.sessions_repo = MagicMock()
    adapter.distractions_repo = MagicMock()
    adapter.profile_repo = MagicMock()
    adapter.follows_repo = MagicMock()
    adapter.reports_service = MagicMock()
    adapter.ranking_service = MagicMock()
    adapter.reminders_service = MagicMock()
    adapter.sessions_service = MagicMock()
    adapter.content_service = MagicMock()
    adapter.time_estimation_service = MagicMock()
    adapter.content_management_service = MagicMock()
    adapter.settings_service = MagicMock()
    adapter.profile_service = MagicMock()
    adapter.social_service = MagicMock()
    adapter.schema_service = MagicMock()
    adapter.query_service = MagicMock()
    adapter.nightly_state_repo = MagicMock()
    return adapter


SIMPLIFIED_TEMPLATE = {
    "template_id": "t-1",
    "title": "Learn Chinese",
    "description": "Practice Mandarin",
    "category": "language",
    "target_value": 3.0,
    "metric_type": "hours",
    "emoji": None,
    "is_active": True,
    "created_at_utc": "2026-01-01",
    "updated_at_utc": "2026-01-01",
}


@pytest.mark.unit
def test_list_templates_no_keyerror_on_simplified_schema():
    adapter = _make_adapter()
    adapter.templates_repo.list_templates.return_value = [dict(SIMPLIFIED_TEMPLATE)]
    adapter.unlocks_service.annotate_templates_with_unlock_status.return_value = [
        {**SIMPLIFIED_TEMPLATE, "unlocked": True, "lock_reason": None}
    ]

    result = adapter.list_templates(user_id=1, category="language")
    assert "Error listing templates" not in result
    assert "Learn Chinese" in result
    assert "3.0h" in result


@pytest.mark.unit
def test_list_templates_no_keyerror_when_template_has_level():
    """Legacy templates that still have level should include it in parentheses."""
    adapter = _make_adapter()
    t = {**SIMPLIFIED_TEMPLATE, "level": "beginner"}
    adapter.templates_repo.list_templates.return_value = [t]
    adapter.unlocks_service.annotate_templates_with_unlock_status.return_value = [
        {**t, "unlocked": True, "lock_reason": None}
    ]

    result = adapter.list_templates(user_id=1)
    assert "(beginner)" in result


@pytest.mark.unit
def test_get_template_no_keyerror_on_simplified_schema():
    adapter = _make_adapter()
    adapter.templates_repo.get_template.return_value = dict(SIMPLIFIED_TEMPLATE)
    adapter.templates_repo.get_prerequisites.return_value = []
    adapter.unlocks_service.get_unlock_status.return_value = {
        "unlocked": True, "lock_reason": None
    }

    result = adapter.get_template(user_id=1, template_id="t-1")
    assert "Error getting template" not in result
    assert "Learn Chinese" in result
    assert "Description: Practice Mandarin" in result
    assert "Level:" not in result
    assert "Done means:" not in result
    assert "Effort:" not in result


@pytest.mark.unit
def test_get_template_includes_target_direction_default():
    adapter = _make_adapter()
    adapter.templates_repo.get_template.return_value = dict(SIMPLIFIED_TEMPLATE)
    adapter.templates_repo.get_prerequisites.return_value = []
    adapter.unlocks_service.get_unlock_status.return_value = {
        "unlocked": True, "lock_reason": None
    }

    result = adapter.get_template(user_id=1, template_id="t-1")
    assert "(at_least)" in result


@pytest.mark.unit
def test_get_template_falls_back_to_why_for_description():
    """Legacy templates have 'why' instead of 'description'."""
    adapter = _make_adapter()
    t = dict(SIMPLIFIED_TEMPLATE)
    del t["description"]
    t["why"] = "Because learning is fun"
    adapter.templates_repo.get_template.return_value = t
    adapter.templates_repo.get_prerequisites.return_value = []
    adapter.unlocks_service.get_unlock_status.return_value = {
        "unlocked": True, "lock_reason": None
    }

    result = adapter.get_template(user_id=1, template_id="t-1")
    assert "Description: Because learning is fun" in result
