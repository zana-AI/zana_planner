import os
import sys


TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.append(TM_BOT_DIR)


from llms.failure_responses import (  # noqa: E402
    classify_tool_error,
    extract_quoted_value,
    render_failure_response,
)


def test_classify_tool_error_known_adapter_strings():
    assert classify_tool_error("Could not parse datetime: 'tomorrow-ish'. Please use a clearer date/time description.") == "time_parse_fail"
    assert classify_tool_error("Missing required arguments for create_reminder: remind_at. Provided: ['text'].") == "missing_arg"
    assert classify_tool_error("No promises found matching 'sport'. Try a different search term.") == "promise_not_found"
    assert classify_tool_error("Promise 'P99' not found.") == "promise_not_found"
    assert classify_tool_error("Error scheduling session: database unavailable") == "internal_error"


def test_extract_quoted_value_from_tool_error():
    assert extract_quoted_value("Could not parse datetime: 'tomorrow 8ish'. Please use a clearer date/time description.") == "tomorrow 8ish"


def test_render_failure_response_uses_friendly_non_technical_text():
    response = render_failure_response(
        "time_parse_fail",
        "en",
        phrase="tomorrow 8ish",
        arg_hint="a clearer time",
    )

    assert "tomorrow 8ish" in response
    assert "datetime" not in response.lower()
    assert "trace" not in response.lower()
