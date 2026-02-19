import pytest

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
