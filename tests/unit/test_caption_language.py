"""Source-language selection must never prefer an uploaded/automatic translation."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "caption_fetch", Path(__file__).parents[2] / "scripts/caption_relay/fetch.py")
fetcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetcher)


def track(language, generated=False):
    return SimpleNamespace(language_code=language, is_generated=generated)


def fmt(language, translated=False):
    return [{"ext": "json3", "url": "https://www.youtube.com/api/timedtext?lang=" + language
             + ("&tlang=en" if translated else "")}]


@pytest.mark.parametrize("source", ["fr", "en", "fa", "de", "ja"])
def test_native_manual_beats_translation_then_native_auto(source):
    translated = track("en-US" if source != "en" else "fr")
    manual, auto = track(source), track(source, True)
    assert fetcher.api_source_tracks([translated, manual, auto]) == [manual, auto]
    assert fetcher.api_source_tracks([translated, auto]) == [auto]


def test_regional_variant_and_ambiguous_tracks():
    manual, auto = track("fr-CA"), track("fr", True)
    assert fetcher.api_source_tracks([track("en-US"), manual, auto]) == [manual, auto]
    assert fetcher.api_source_tracks([track("en"), track("fr")]) == []
    assert fetcher.api_source_tracks([track("en", True), track("fr", True)]) == []
    assert fetcher.api_source_tracks([]) == []


def test_ytdlp_excludes_translations_and_prefers_native_manual():
    info = {"subtitles": {"en-US": fmt("en-US"), "fr": fmt("fr")},
            "automatic_captions": {"en": fmt("fr", True), "fr-orig": fmt("fr")}}
    candidates = fetcher.ytdlp_source_tracks(info)
    assert [(lang, auto) for lang, auto, _ in candidates] == [("fr", False), ("fr", True)]


def test_translated_url_is_never_a_candidate_even_if_label_matches():
    info = {"subtitles": {"fr": fmt("en", True)},
            "automatic_captions": {"fr-orig": fmt("fr")}}
    assert [(lang, auto) for lang, auto, _ in fetcher.ytdlp_source_tracks(info)] == [("fr", True)]


def test_original_audio_metadata_overrides_dubbed_asr_tracks():
    info = {"automatic_captions": {"en-orig": fmt("en"), "fr-orig": fmt("fr")},
            "formats": [{"acodec": "opus", "language": "fr", "language_preference": 10},
                        {"acodec": "opus", "language": "en", "language_preference": 5}]}
    assert [lang for lang, _, _ in fetcher.ytdlp_source_tracks(info)] == ["fr"]
    info["formats"] = []
    assert fetcher.ytdlp_source_tracks(info) == []


def test_manual_only_requires_audio_language_not_subtitle_list_order():
    info = {"subtitles": {"en": fmt("en"), "fr": fmt("fr")}}
    assert fetcher.ytdlp_source_tracks(info) == []
    info["formats"] = [{"acodec": "opus", "language": "fr"}]
    assert [lang for lang, _, _ in fetcher.ytdlp_source_tracks(info)] == ["fr"]
    info["subtitles"].pop("fr")
    assert fetcher.ytdlp_source_tracks(info) == []


def test_api_failure_stays_in_source_language(monkeypatch):
    calls = []
    class Track:
        def __init__(self, lang, generated=False):
            self.language_code, self.is_generated = lang, generated
        def fetch(self):
            calls.append(self.language_code)
            if not self.is_generated:
                raise RuntimeError("manual download failed")
            class Transcript(list):
                language_code = "fr"
                is_generated = True
            return Transcript([SimpleNamespace(start=0, duration=2, text="Bonjour")])
    monkeypatch.setitem(sys.modules, "youtube_transcript_api", SimpleNamespace(
        YouTubeTranscriptApi=lambda **kwargs: SimpleNamespace(list=lambda _: [
            Track("en-US"), Track("fr"), Track("fr", True)])))
    result = fetcher.fetch("q_r7L1wsY2U")
    assert result["transcript"]["language"] == "fr"
    assert calls == ["fr", "fr"]


def test_ytdlp_fallback_downloads_only_native_caption(monkeypatch):
    class Blocked:
        def __init__(self, **kwargs):
            raise RuntimeError("blocked")
    monkeypatch.setitem(sys.modules, "youtube_transcript_api", SimpleNamespace(YouTubeTranscriptApi=Blocked))
    class YDL:
        def __init__(self, *_): pass
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def extract_info(self, *args, **kwargs):
            return {"subtitles": {"en": fmt("en")}, "automatic_captions": {
                "en": fmt("fr", True), "fr-orig": fmt("fr")}}
        def urlopen(self, url):
            assert url.endswith("lang=fr")
            return SimpleNamespace(read=lambda _: json.dumps({"events": [{
                "tStartMs": 0, "dDurationMs": 2000, "segs": [{"utf8": "Bonjour"}]}]}).encode())
    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=YDL))
    result = fetcher.fetch("q_r7L1wsY2U")["transcript"]
    assert result == {"language": "fr", "is_generated": True,
                      "cues": [{"start": 0, "end": 2, "text": "Bonjour"}]}
