from pathlib import Path

from ui.content_copy import persian_video_card, youtube_actions


def test_persian_actions_match_library_and_viewer_vocabulary():
    labels = youtube_actions('fa')
    assert labels['save'] == '➕ ذخیره در کتابخانه'
    assert labels['watch'] == '▶️ تماشای ویدیو'
    assert set(labels) == set(youtube_actions('en'))
    assert youtube_actions('unknown') == youtube_actions('en')


def test_persian_card_keeps_original_title_and_does_not_promise_captions():
    message = persian_video_card({'title': "Joey Doesn't Share Food", 'channel': 'Friends', 'duration_seconds': 169})
    assert "Joey Doesn't Share Food" in message
    assert 'Friends' in message
    assert '2:49' in message
    assert 'کتابخانه' in message
    assert 'زیرنویس' not in message


def test_unknown_duration_is_not_invented_and_long_titles_are_bounded():
    assert 'مدت:' not in persian_video_card({})
    assert 'x' * 121 not in persian_video_card({'title': 'x' * 180})


def test_bot_preserves_handwritten_persian_and_passes_viewer_language():
    source = (Path(__file__).resolve().parents[2] / 'tm_bot/handlers/message_handlers.py').read_text(encoding='utf-8')
    assert 'auto_translate=video_ui_language != "fa"' in source
    assert '"lang": video_ui_language' in source
    assert 'keyboard_rows.insert(0,' in source
