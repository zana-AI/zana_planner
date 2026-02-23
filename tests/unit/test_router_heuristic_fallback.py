import os
import sys

TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.append(TM_BOT_DIR)

from llms.agent import _heuristic_route_decision_from_text  # noqa: E402


def test_router_heuristic_fallback_is_engagement_for_transactional_phrase():
    route = _heuristic_route_decision_from_text("please add a promise to run 3 hours this week")
    assert route.mode == "engagement"
    assert route.reason == "parsing_failed_fallback"


def test_router_heuristic_fallback_is_engagement_for_advice_phrase():
    route = _heuristic_route_decision_from_text("what should I focus on next week to improve progress?")
    assert route.mode == "engagement"
    assert route.reason == "parsing_failed_fallback"


def test_router_heuristic_fallback_is_engagement_for_social_phrase():
    route = _heuristic_route_decision_from_text("show me my followers and community feed")
    assert route.mode == "engagement"
    assert route.reason == "parsing_failed_fallback"


def test_router_heuristic_fallback_is_engagement_for_short_casual_phrase():
    route = _heuristic_route_decision_from_text("hey there")
    assert route.mode == "engagement"
    assert route.reason == "parsing_failed_fallback"
