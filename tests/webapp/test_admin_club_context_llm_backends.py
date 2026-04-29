from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

pytest.importorskip("fastapi")

from fastapi import HTTPException  # noqa: E402
from webapp.routers import admin as admin_router  # noqa: E402
from webapp.schemas import AdminLLMBackendTestRequest, UpdateClubContextRequest  # noqa: E402


def test_update_club_context_request_validates_lengths():
    payload = UpdateClubContextRequest(
        description="Mutual-aid club",
        club_goal="Make weekly care visible",
        vibe="Warm and practical",
        checkin_what_counts="One concrete act of help",
    )

    assert payload.club_goal == "Make weekly care visible"

    with pytest.raises(ValidationError):
        UpdateClubContextRequest(vibe="x" * 501)


def test_admin_club_setup_mapping_includes_context_fields():
    summary = admin_router._admin_club_setup_from_row(
        {
            "club_id": "club-1",
            "name": "Care Circle",
            "visibility": "private",
            "member_count": 3,
            "telegram_status": "ready",
            "telegram_invite_link": "https://t.me/+care",
            "promise_id": "promise-1",
            "promise_text": "Do one helpful thing",
            "target_count_per_week": 1,
            "owner_user_id": "42",
            "owner_name": "Ebrahim",
            "created_at_utc": "2026-01-01T00:00:00Z",
            "telegram_requested_at_utc": "2026-01-02T00:00:00Z",
            "telegram_ready_at_utc": "2026-01-03T00:00:00Z",
            "description": "A club for small acts of mutual aid.",
            "club_goal": "Turn intention into one visible act of care each week.",
            "vibe": "Warm, practical, gently accountable.",
            "checkin_what_counts": "A concrete action for another person or community.",
        }
    )

    assert summary.description == "A club for small acts of mutual aid."
    assert summary.club_goal == "Turn intention into one visible act of care each week."
    assert summary.vibe == "Warm, practical, gently accountable."
    assert summary.checkin_what_counts == "A concrete action for another person or community."


@pytest.mark.asyncio
async def test_llm_backends_status_uses_booleans_and_masks_config_errors(monkeypatch):
    secret = "sk-test-secret-1234567890"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    monkeypatch.delenv("GCP_CREDENTIALS_B64", raising=False)

    def _raise_config_error():
        raise ValueError(f"bad credential {secret}")

    monkeypatch.setattr(admin_router, "load_llm_env", _raise_config_error)

    response = await admin_router.get_llm_backends(admin_id=1)

    assert response["credentials"]["openai"] is True
    assert response["credentials"]["deepseek"] is False
    assert all(isinstance(value, bool) for value in response["credentials"].values())
    assert secret not in json.dumps(response)
    assert "[masked]" in response["config_error"]


@pytest.mark.asyncio
async def test_llm_backend_test_rejects_missing_credentials(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        await admin_router.test_llm_backend(
            AdminLLMBackendTestRequest(provider="openai", model="gpt-4o-mini", role="responder"),
            admin_id=1,
        )

    assert exc_info.value.status_code == 400
    assert "credentials are not configured" in exc_info.value.detail


@pytest.mark.asyncio
async def test_llm_backend_test_rejects_unsupported_model(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")

    with pytest.raises(HTTPException) as exc_info:
        await admin_router.test_llm_backend(
            AdminLLMBackendTestRequest(provider="groq", model="not-a-coded-model", role="responder"),
            admin_id=1,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Unsupported model for this prototype"
