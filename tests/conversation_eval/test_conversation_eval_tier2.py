"""
Tier-2 conversation eval: real router + planner LLMs, real DB.
Validates routing correctness and datetime resolution confidence.

Requires: GROQ_API_KEY (or OPENAI_API_KEY) + DATABASE_URL_STAGING or DATABASE_URL_PROD.
Run with:
    pytest tests/conversation_eval/test_conversation_eval_tier2.py -v -m e2e
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.insert(0, TM_BOT_DIR)

from tests.conversation_eval.harness import load_transcript, run_tier2
from tests.test_config import ensure_users_exist, unique_user_id
from services.planner_api_adapter import PlannerAPIAdapter

pytestmark = [pytest.mark.e2e, pytest.mark.requires_postgres]

TRANSCRIPTS_DIR = Path(__file__).resolve().parent / "transcripts"


def _list_tier2_transcripts():
    if not TRANSCRIPTS_DIR.is_dir():
        return []
    files = sorted(TRANSCRIPTS_DIR.glob("t2_*.yaml")) + sorted(TRANSCRIPTS_DIR.glob("t2_*.yml"))
    return files


@pytest.mark.e2e
@pytest.mark.requires_postgres
@pytest.mark.parametrize("transcript_path", _list_tier2_transcripts(), ids=lambda p: p.stem)
def test_conversation_eval_tier2(transcript_path: Path, tmp_path):
    """Run a Tier-2 transcript through real LLMs and assert routing + tool coverage."""
    transcript = load_transcript(transcript_path)
    if transcript.get("tier") != 2:
        pytest.skip("Not a Tier-2 transcript")
    turns = transcript.get("turns") or []
    if not turns:
        pytest.skip("Transcript has no turns")

    has_llm_key = bool(
        os.environ.get("GROQ_API_KEY") or os.environ.get("OPENAI_API_KEY")
    )
    if not has_llm_key:
        pytest.skip("No LLM API key available — set GROQ_API_KEY or OPENAI_API_KEY")

    user_id = unique_user_id()
    ensure_users_exist(user_id)
    adapter = PlannerAPIAdapter(str(tmp_path))

    result = run_tier2(transcript, adapter, user_id)

    assert not result.errors, (
        f"[{transcript_path.stem}] Errors:\n"
        + "\n".join(f"  - {e}" for e in result.errors)
        + f"\n\nPer-turn responses:\n"
        + "\n".join(f"  Turn {i+1}: {r!r}" for i, r in enumerate(result.per_turn_responses))
    )
    assert result.passed, (
        f"[{transcript_path.stem}] rubric_scores={result.rubric_scores}"
    )
