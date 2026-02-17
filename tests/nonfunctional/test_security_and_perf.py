import pytest

from llms.tool_wrappers import _sanitize_user_id


@pytest.mark.nonfunctional
def test_sanitize_user_id_blocks_non_digits():
    with pytest.raises(ValueError):
        _sanitize_user_id("1../2")
    with pytest.raises(ValueError):
        _sanitize_user_id("abc")


@pytest.mark.nonfunctional
def test_message_format_response_escapes_html_in_llm_and_log():
    from utils.formatting import format_response_html

    out = format_response_html("<img src=x onerror=alert(1)>", {"k": "<b>v</b>"})
    assert "<img" not in out
    assert "&lt;img" in out
    assert "&lt;b&gt;v&lt;/b&gt;" in out


@pytest.mark.nonfunctional
def test_url_detection_handles_large_text():
    from services.content_service import ContentService

    svc = ContentService()
    text = "a" * 200_000 + " https://example.com/path?x=1 " + "b" * 200_000
    urls = svc.detect_urls(text)
    assert urls == ["https://example.com/path?x=1"]
