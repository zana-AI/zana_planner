import os
import sys

TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.append(TM_BOT_DIR)

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from llms.agent import (  # noqa: E402
    _heuristic_route_decision_from_text,
    _sanitize_router_history,
)


def test_router_heuristic_fallback_detects_operator_for_transactional_phrase():
    route = _heuristic_route_decision_from_text("please add a promise to run 3 hours this week")
    assert route.mode == "operator"
    assert route.reason == "keyword_operator_fallback"


def test_router_heuristic_fallback_detects_strategist_for_advice_phrase():
    route = _heuristic_route_decision_from_text("what should I focus on next week to improve progress?")
    assert route.mode == "strategist"
    assert route.reason == "keyword_strategist_fallback"


def test_router_heuristic_fallback_detects_social_for_social_phrase():
    route = _heuristic_route_decision_from_text("show me my followers and community feed")
    assert route.mode == "social"
    assert route.reason == "keyword_social_fallback"




def test_router_heuristic_fallback_detects_operator_for_persian_transactional_phrase():
    route = _heuristic_route_decision_from_text("یه تسک جدید اضافه کن")
    assert route.mode == "operator"
    assert route.reason == "keyword_operator_fallback"


def test_router_heuristic_fallback_is_engagement_for_short_casual_phrase():
    route = _heuristic_route_decision_from_text("hey there")
    assert route.mode == "engagement"
    assert route.reason == "parsing_failed_fallback"


def test_sanitize_router_history_drops_tool_and_protocol_artifacts():
    messages = [
        HumanMessage(content="what is p09"),
        AIMessage(content="(calling tool)", tool_calls=[{"name": "memory_search", "args": {}, "id": "c1"}]),
        ToolMessage(content='{"result":"ok"}', tool_call_id="c1"),
        AIMessage(content="<|DSML|function_calls>\n<|DSML|invoke name='web_fetch'>\n</|DSML|invoke>"),
        AIMessage(content="Sure, I can help with that."),
    ]
    out = _sanitize_router_history(messages, max_messages=8)
    assert len(out) == 2
    assert isinstance(out[0], HumanMessage)
    assert isinstance(out[1], AIMessage)
    assert "help with that" in str(out[1].content)


def test_sanitize_router_history_applies_tail_limit():
    messages = [HumanMessage(content=f"m{i}") for i in range(12)]
    out = _sanitize_router_history(messages, max_messages=5)
    assert len(out) == 5
    assert str(out[0].content) == "m7"
    assert str(out[-1].content) == "m11"
