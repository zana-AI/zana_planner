"""Handler tests for the 'track as one-time' confirmation button."""
import pytest


@pytest.mark.handler
def test_confirmation_kb_adds_one_time_button_for_schedule_session():
    pytest.importorskip("telegram")
    pytest.importorskip("langgraph.prebuilt")
    from handlers.message_handlers import MessageHandlers

    mh = MessageHandlers.__new__(MessageHandlers)  # no __init__ side effects

    kb = mh._mutation_confirmation_kb(None, {"tool_name": "schedule_session"})
    buttons = [b for row in kb.inline_keyboard for b in row]
    # Yes, Skip, and the extra one-time button.
    assert len(buttons) == 3

    kb2 = mh._mutation_confirmation_kb(None, {"tool_name": "log_completed_activity"})
    buttons2 = [b for row in kb2.inline_keyboard for b in row]
    assert len(buttons2) == 2  # only Yes / Skip

    # No pending → safe default of Yes / Skip only.
    kb3 = mh._mutation_confirmation_kb(None, None)
    buttons3 = [b for row in kb3.inline_keyboard for b in row]
    assert len(buttons3) == 2
