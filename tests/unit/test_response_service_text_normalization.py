import pytest


@pytest.mark.unit
def test_normalize_non_html_entities_decodes_quote_entities_for_plain_text():
    pytest.importorskip("telegram")
    from services.response_service import ResponseService

    raw = "reply &#x27;yes&#x27; or &#39;confirm&#39; and &quot;ok&quot;"
    out = ResponseService._normalize_non_html_entities(raw, parse_mode=None)
    assert out == "reply 'yes' or 'confirm' and \"ok\""


@pytest.mark.unit
def test_normalize_non_html_entities_keeps_html_mode_unchanged():
    pytest.importorskip("telegram")
    from services.response_service import ResponseService

    raw = "<b>Xaana:</b>\nTap &#x27;Yes&#x27;."
    out = ResponseService._normalize_non_html_entities(raw, parse_mode="HTML")
    assert out == raw
