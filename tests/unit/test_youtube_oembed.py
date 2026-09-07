from utils import youtube_utils


class _Response:
    status_code = 200

    @staticmethod
    def json():
        return {"title": "A useful French lesson", "author_name": "French Channel"}


def test_oembed_supplies_title_when_video_page_is_blocked(monkeypatch):
    monkeypatch.setattr(youtube_utils, "YT_DLP_AVAILABLE", False)
    monkeypatch.setattr(youtube_utils.requests, "get", lambda *args, **kwargs: _Response())
    monkeypatch.setattr(youtube_utils, "_get_video_info_basic", lambda _url, result: result)

    result = youtube_utils.get_video_info("i1rkMaXuiLo")

    assert result["title"] == "A useful French lesson"
    assert result["channel"] == "French Channel"
