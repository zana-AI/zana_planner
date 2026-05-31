"""Unit tests for resolve_promise_with_llm (semantic promise matching).

Uses a fake model so the tests are deterministic and offline.
"""
import json
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tm_bot"))
from llms.resolvers import resolve_promise_with_llm  # noqa: E402

pytestmark = pytest.mark.unit

PROMISES = [
    {"id": "P07", "text": "Home_chores_/_Cooking"},
    {"id": "P08", "text": "Practice_French/English"},
    {"id": "P09", "text": "Play_piano"},
    {"id": "P20", "text": "Study_English"},
]


class FakeModel:
    """Returns a fixed reply (str) for every invoke; or raises if reply is an Exception."""

    def __init__(self, reply):
        self._reply = reply

    def invoke(self, messages):
        if isinstance(self._reply, Exception):
            raise self._reply
        return types.SimpleNamespace(content=self._reply)


def _resolve(reply, query="something", promises=PROMISES):
    return json.loads(resolve_promise_with_llm(FakeModel(reply), query, promises))


def test_high_confidence_valid_id_passes_through():
    out = _resolve('{"resolved": "P07", "confidence": "high"}', "cook dinner")
    assert out == {"resolved": "P07", "confidence": "high"}


def test_high_confidence_unknown_id_is_demoted_to_none():
    # Model hallucinates an id that isn't in the promise set.
    out = _resolve('{"resolved": "P99", "confidence": "high"}')
    assert out == {"resolved": None, "confidence": "none"}


def test_low_confidence_keeps_only_valid_candidates():
    out = _resolve(
        '{"resolved": null, "confidence": "low", '
        '"candidates": ["P08", "P20", "P99"], "clarification": "Which one?"}',
        "english",
    )
    assert out["confidence"] == "low"
    assert out["candidates"] == ["P08", "P20"]  # P99 filtered out
    assert out["clarification"] == "Which one?"


def test_low_confidence_with_no_valid_candidates_becomes_none():
    out = _resolve('{"resolved": null, "confidence": "low", "candidates": ["P99"]}')
    assert out == {"resolved": None, "confidence": "none"}


def test_none_confidence_passes_through():
    out = _resolve('{"resolved": null, "confidence": "none"}', "dentist appointment")
    assert out == {"resolved": None, "confidence": "none"}


def test_markdown_fenced_json_is_parsed():
    out = _resolve('```json\n{"resolved": "P09", "confidence": "high"}\n```', "piano")
    assert out == {"resolved": "P09", "confidence": "high"}


def test_malformed_model_output_returns_none():
    out = _resolve("not json at all")
    assert out == {"resolved": None, "confidence": "none"}


def test_model_exception_returns_none():
    out = _resolve(RuntimeError("boom"))
    assert out == {"resolved": None, "confidence": "none"}


def test_empty_query_short_circuits_without_model_call():
    out = _resolve('{"resolved": "P07", "confidence": "high"}', query="   ")
    assert out == {"resolved": None, "confidence": "none"}


def test_no_promises_short_circuits():
    out = json.loads(resolve_promise_with_llm(FakeModel('{"resolved": "P07", "confidence": "high"}'), "cook", []))
    assert out == {"resolved": None, "confidence": "none"}
