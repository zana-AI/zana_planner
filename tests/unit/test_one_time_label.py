"""Unit tests for the one-time promise label derivation (agent._one_time_label_from)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tm_bot"))
from llms.agent import _one_time_label_from  # noqa: E402

pytestmark = pytest.mark.unit


def test_prefers_session_title():
    assert _one_time_label_from({"title": "Cook tuna"}, "rambly message ignored") == "Cook tuna"


def test_title_truncated_to_60():
    assert len(_one_time_label_from({"title": "x" * 100}, "")) == 60


def test_extracts_i_want_to_phrase_when_no_title():
    assert "read a book" in _one_time_label_from({}, "I want to read a book")


def test_snippet_fallback_when_no_pattern():
    out = _one_time_label_from({}, "okay i am going to cook something tonight for dinner")
    assert out and len(out) <= 60 and out != "One-time session"


def test_default_when_empty():
    assert _one_time_label_from({}, "") == "One-time session"
    assert _one_time_label_from({}, "   ") == "One-time session"
