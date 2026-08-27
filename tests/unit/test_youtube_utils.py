import pytest

import utils.youtube_utils as youtube_utils
from utils.youtube_utils import extract_video_id


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw",
    [
        "https://www.youtube.com/watch?v=1ZhsdckCK2c",
        "https://www.youtube.com/watch?v=1ZhsdckCK2c&t=42",
        "https://youtu.be/1ZhsdckCK2c",
        "https://youtube.com/embed/1ZhsdckCK2c?si=test",
        "Please watch this https://www.youtube.com/watch?v=1ZhsdckCK2c now",
    ],
)
def test_extract_video_id_returns_exact_video_id(raw):
    assert extract_video_id(raw) == "1ZhsdckCK2c"


@pytest.mark.unit
def test_extract_video_id_rejects_invalid_or_missing_id():
    assert extract_video_id("https://example.com/watch?v=1ZhsdckCK2c") is None
    assert extract_video_id("https://www.youtube.com/watch?v=short") is None
    assert extract_video_id("") is None


@pytest.mark.unit
def test_parse_vtt_cues_normalizes_timestamps_and_markup():
    raw = """WEBVTT\n\n00:00:01.000 --> 00:00:03.500\n<c.green>Hello &amp; welcome</c>\n\n00:00:04.000 --> 00:00:05.000\nNext cue\n"""
    assert youtube_utils._parse_vtt_cues(raw) == [
        {"start": 1.0, "end": 3.5, "text": "Hello & welcome"},
        {"start": 4.0, "end": 5.0, "text": "Next cue"},
    ]


@pytest.mark.unit
def test_get_video_transcript_uses_caption_track_without_downloading_video(monkeypatch):
    class FakeResponse:
        def read(self):
            return b"WEBVTT\n\n00:00.000 --> 00:01.000\nA short lesson\n"

    class FakeYDL:
        def __init__(self, _opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, download=False):
            assert download is False
            return {"subtitles": {"en": [{"ext": "vtt", "url": "https://caption.test/en.vtt"}]}}

        def urlopen(self, url):
            assert url.endswith("en.vtt")
            return FakeResponse()

    monkeypatch.setattr(youtube_utils, "YT_DLP_AVAILABLE", True)
    monkeypatch.setattr(youtube_utils.yt_dlp, "YoutubeDL", FakeYDL)
    result = youtube_utils.get_video_transcript("abcdefghijk")
    assert result["available"] is True
    assert result["source"] == "manual"
    assert result["cues"][0]["text"] == "A short lesson"
