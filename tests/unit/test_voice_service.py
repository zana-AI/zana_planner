import pytest

from services.voice_service import VoiceService


@pytest.mark.unit
def test_clean_text_for_tts_strips_html_and_section_labels():
    raw = (
        "<b>Xaana:</b>\n"
        "Hello <i>world</i>!\n"
        "\n"
        "<b>Log:</b>\n"
        "<blockquote expandable>did something &amp; more</blockquote>"
    )
    cleaned = VoiceService.clean_text_for_tts(raw)
    # No HTML tags/header/log section; only user-facing response text remains.
    assert "<" not in cleaned and ">" not in cleaned
    assert "Xaana" not in cleaned
    assert "Log" not in cleaned
    assert "Hello" in cleaned
    assert "world" in cleaned
    assert "did something" not in cleaned
    assert "&" not in cleaned


@pytest.mark.unit
def test_clean_text_for_tts_strips_markdown_formatting():
    raw = "**Bold** _italic_ `code` [Link](https://example.com)\n- item"
    cleaned = VoiceService.clean_text_for_tts(raw)
    assert "**" not in cleaned
    assert "_" not in cleaned
    assert "`" not in cleaned
    assert "Link" in cleaned
    assert "item" in cleaned


@pytest.mark.unit
def test_clean_text_for_tts_removes_structured_markdown_log_block():
    raw = (
        "*Xaana:*\n"
        "`Great progress today.`\n\n"
        "*Log:*\n"
        "debug: trace_id=abc123\n"
        "tool output: {'ok': true}\n"
    )
    cleaned = VoiceService.clean_text_for_tts(raw)
    assert "Great progress today" in cleaned
    assert "Xaana" not in cleaned
    assert "Log" not in cleaned
    assert "trace_id" not in cleaned
    assert "tool output" not in cleaned
