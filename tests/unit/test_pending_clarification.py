import os
import sys

TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.append(TM_BOT_DIR)


from handlers.message_handlers import MessageHandlers  # noqa: E402


class _FakeLLMHandler:
    def __init__(self):
        self.chat_model = None  # disables LLM extraction fallback


def test_parse_slot_fill_values_key_value_lines():
    mh = MessageHandlers.__new__(MessageHandlers)  # bypass __init__
    mh.llm_handler = _FakeLLMHandler()

    out = mh._parse_slot_fill_values(
        user_text="setting_key: language\nother: ignored",
        missing_fields=["setting_key", "setting_value"],
        user_id=123,
        user_lang_code="en",
    )
    assert out.get("setting_key") == "language"
    assert "setting_value" not in out


def test_parse_slot_fill_values_single_field_uses_whole_message():
    mh = MessageHandlers.__new__(MessageHandlers)  # bypass __init__
    mh.llm_handler = _FakeLLMHandler()

    out = mh._parse_slot_fill_values(
        user_text="P01",
        missing_fields=["promise_id"],
        user_id=123,
        user_lang_code="en",
    )
    assert out.get("promise_id") == "P01"


def test_choose_from_options_supports_index_and_fuzzy_title():
    options = [
        {"promise_id": "P10", "title": "Do sport"},
        {"promise_id": "P11", "title": "Sport cardio"},
    ]

    assert MessageHandlers._choose_from_options("P10", options) == "P10"
    assert MessageHandlers._choose_from_options("1", options) == "P10"
    assert MessageHandlers._choose_from_options("cardio", options) == "P11"




