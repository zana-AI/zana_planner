import os
import sys

import pytest

TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.append(TM_BOT_DIR)

from llms.agent import _parse_plan, _parse_route_decision  # noqa: E402


def test_parse_plan_plain_json():
    payload = (
        '{"steps":[{"kind":"respond","purpose":"Answer user.","response_hint":"Keep it short."}],'
        '"detected_intent":"QUERY_PROGRESS","intent_confidence":"high","safety":{"requires_confirmation":false}}'
    )
    plan = _parse_plan(payload)
    assert len(plan.steps) == 1
    assert plan.steps[0].kind == "respond"
    assert plan.detected_intent == "QUERY_PROGRESS"


def test_parse_plan_fenced_json():
    payload = """```json
{"steps":[{"kind":"tool","purpose":"Lookup","tool_name":"count_promises","tool_args":{}}]}
```"""
    plan = _parse_plan(payload)
    assert len(plan.steps) == 1
    assert plan.steps[0].tool_name == "count_promises"


def test_parse_plan_content_blocks():
    payload = [
        {"type": "text", "text": "Here is the plan:"},
        {
            "type": "text",
            "text": '{"steps":[{"kind":"respond","purpose":"Final answer","response_hint":"Friendly"}]}',
        },
    ]
    plan = _parse_plan(payload)
    assert len(plan.steps) == 1
    assert plan.steps[0].kind == "respond"


def test_parse_plan_rejects_malformed_payload():
    with pytest.raises(Exception):
        _parse_plan("totally not json")


def test_parse_route_decision_from_blocks():
    payload = [
        {"type": "text", "text": "Routing result:"},
        {"type": "text", "text": '{"mode":"operator","confidence":"high","reason":"transactional_intent"}'},
    ]
    route = _parse_route_decision(payload)
    assert route.mode == "operator"
    assert route.confidence == "high"

