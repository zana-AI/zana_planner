"""
Conversation eval tests: parametrized over transcript YAML files; run Tier 1 harness and assert rubric.
"""

import os
import sys
from pathlib import Path

import pytest

# Ensure tm_bot and tests on path
TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.insert(0, TM_BOT_DIR)

from tests.conversation_eval.harness import load_transcript, run_tier1
from tests.test_config import ensure_users_exist, unique_user_id
from services.planner_api_adapter import PlannerAPIAdapter

pytestmark = [pytest.mark.integration, pytest.mark.requires_postgres]

TRANSCRIPTS_DIR = Path(__file__).resolve().parent / "transcripts"


def _list_transcript_files():
    if not TRANSCRIPTS_DIR.is_dir():
        return []
    return sorted(TRANSCRIPTS_DIR.glob("*.yaml")) + sorted(TRANSCRIPTS_DIR.glob("*.yml"))


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.parametrize("transcript_path", _list_transcript_files(), ids=lambda p: p.stem)
def test_conversation_eval_transcript(transcript_path: Path, tmp_path):
    """Run a single transcript through Tier 1 harness and assert passed + rubric."""
    transcript = load_transcript(transcript_path)
    if transcript.get("tier") != 1:
        pytest.skip("Only Tier 1 transcripts run in this suite")
    turns = transcript.get("turns") or []
    if not turns:
        pytest.skip("Transcript has no turns")

    user_id = unique_user_id()
    ensure_users_exist(user_id)
    adapter = PlannerAPIAdapter(str(tmp_path))

    result = run_tier1(transcript, adapter, user_id)

    assert not result.errors, f"Run had errors: {result.errors}"
    assert result.passed, (
        f"Eval failed: rubric_scores={result.rubric_scores}, "
        f"per_turn_responses={result.per_turn_responses}"
    )
