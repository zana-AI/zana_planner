"""
Unit tests for memory module: config, read, search, flush.
"""

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from memory.config import get_memory_root, is_flush_enabled, is_memory_configured
from memory.flush import (
    DEFAULT_MEMORY_FLUSH_SOFT_TOKENS,
    resolve_memory_flush_prompt,
    resolve_memory_flush_system_prompt,
    run_memory_flush,
    should_run_memory_flush,
)
from memory.read import memory_get
from memory.search import memory_search


@pytest.mark.unit
def test_is_memory_configured_unset(monkeypatch):
    monkeypatch.delenv("MEMORY_VECTOR_DB_URL", raising=False)
    assert is_memory_configured() is False


@pytest.mark.unit
def test_is_memory_configured_set(monkeypatch):
    monkeypatch.setenv("MEMORY_VECTOR_DB_URL", "http://localhost:8000")
    try:
        assert is_memory_configured() is True
    finally:
        monkeypatch.delenv("MEMORY_VECTOR_DB_URL", raising=False)


@pytest.mark.unit
def test_get_memory_root_per_user():
    root = Path(tempfile.gettempdir()) / "zana_mem_test"
    root.mkdir(exist_ok=True)
    try:
        user_root = get_memory_root(str(root), "12345")
        assert user_root == root / "users" / "12345"
        assert get_memory_root(root, "999") == root / "users" / "999"
    finally:
        if root.exists():
            root.rmdir()


@pytest.mark.unit
def test_get_memory_root_rejects_invalid_user_id():
    with pytest.raises(ValueError):
        get_memory_root("/tmp", "..")
    with pytest.raises(ValueError):
        get_memory_root("/tmp", "a/b")


@pytest.mark.unit
def test_memory_search_returns_disabled_when_not_configured(monkeypatch):
    monkeypatch.delenv("MEMORY_VECTOR_DB_URL", raising=False)
    out = memory_search("test query", "/tmp", "123")
    assert out.get("disabled") is True
    assert out.get("results") == []
    assert "error" in out


@pytest.mark.unit
def test_memory_get_reads_file(tmp_path):
    user_root = tmp_path / "users" / "42"
    user_root.mkdir(parents=True)
    (user_root / "MEMORY.md").write_text("Hello from MEMORY", encoding="utf-8")
    (user_root / "memory").mkdir()
    (user_root / "memory" / "2025-02-19.md").write_text("Date log", encoding="utf-8")

    out = memory_get("MEMORY.md", str(tmp_path), "42")
    assert out.get("path") == "MEMORY.md"
    assert out.get("text") == "Hello from MEMORY"
    assert "error" not in out or out.get("error") is None

    out2 = memory_get("memory/2025-02-19.md", tmp_path, "42")
    assert out2.get("text") == "Date log"


@pytest.mark.unit
def test_memory_get_missing_file(tmp_path):
    out = memory_get("MEMORY.md", str(tmp_path), "99")
    assert out.get("text") == ""
    assert "error" in out


@pytest.mark.unit
def test_memory_get_rejects_path_traversal(tmp_path):
    out = memory_get("../../../etc/passwd", str(tmp_path), "42")
    assert out.get("error")
    assert "text" in out


@pytest.mark.unit
def test_memory_get_slice_by_lines(tmp_path):
    user_root = tmp_path / "users" / "1"
    user_root.mkdir(parents=True)
    (user_root / "MEMORY.md").write_text("L1\nL2\nL3\nL4\nL5", encoding="utf-8")
    out = memory_get("MEMORY.md", str(tmp_path), "1", from_line=2, lines=2)
    assert out.get("text") == "L2\nL3"


@pytest.mark.unit
def test_resolve_memory_flush_prompt_replaces_date():
    prompt = resolve_memory_flush_prompt(
        now_utc=datetime(2025, 2, 19, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert "2025-02-19" in prompt
    assert "YYYY-MM-DD" not in prompt


@pytest.mark.unit
def test_resolve_memory_flush_system_prompt_contains_silent_hint():
    prompt = resolve_memory_flush_system_prompt()
    assert "silent" in prompt.lower() or "<silent>" in prompt


@pytest.mark.unit
def test_should_run_memory_flush_false_when_under_threshold():
    assert (
        should_run_memory_flush(
            entry={"total_tokens": 1000},
            context_window_tokens=128000,
            reserve_tokens_floor=2048,
            soft_threshold_tokens=DEFAULT_MEMORY_FLUSH_SOFT_TOKENS,
        )
        is False
    )


@pytest.mark.unit
def test_should_run_memory_flush_true_when_over_threshold():
    assert (
        should_run_memory_flush(
            entry={"total_tokens": 125000},
            context_window_tokens=128000,
            reserve_tokens_floor=2048,
            soft_threshold_tokens=DEFAULT_MEMORY_FLUSH_SOFT_TOKENS,
        )
        is True
    )


@pytest.mark.unit
def test_should_run_memory_flush_false_when_already_flushed_this_compaction():
    assert (
        should_run_memory_flush(
            entry={
                "total_tokens": 125000,
                "compaction_count": 1,
                "memory_flush_compaction_count": 1,
            },
            context_window_tokens=128000,
            reserve_tokens_floor=2048,
            soft_threshold_tokens=DEFAULT_MEMORY_FLUSH_SOFT_TOKENS,
        )
        is False
    )


@pytest.mark.unit
def test_run_memory_flush_appends_to_date_file(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMORY_FLUSH_ENABLED", "1")
    calls = []

    def fake_llm(system: str, user: str) -> str:
        calls.append((system, user))
        return "User prefers morning standups."

    run_memory_flush(
        str(tmp_path),
        "42",
        run_flush_llm=fake_llm,
        now_utc=datetime(2025, 2, 19, tzinfo=timezone.utc),
    )
    assert len(calls) == 1
    assert "2025-02-19" in calls[0][1]
    target = tmp_path / "users" / "42" / "memory" / "2025-02-19.md"
    assert target.exists()
    assert "User prefers morning standups" in target.read_text(encoding="utf-8")
