"""Bounded subprocess entry point, shared by cloud and residential workers."""
import json
import re
import sys
from urllib.parse import parse_qs, urlsplit


def _language(code):
    return (code or "").removesuffix("-orig").lower()


def _base(code):
    return _language(code).split("-")[0]


def _unique_language(codes):
    languages = {_base(code) for code in codes if code and _base(code) != "und"}
    return next(iter(languages)) if len(languages) == 1 else None


def api_source_tracks(tracks):
    """ASR tracks identify speech language; uploaded tracks may be translations.

    Multiple ASR languages can mean dubbed audio. Defer ambiguous/manual-only
    listings to yt-dlp's audio metadata instead of guessing from list order.
    """
    source = _unique_language(t.language_code for t in tracks if t.is_generated)
    if not source:
        return []
    return sorted((t for t in tracks if _base(t.language_code) == source),
                  key=lambda t: t.is_generated)


def ytdlp_source_tracks(info):
    """Return only untranslated captions matching the original audio language."""
    tracks = []
    for store, generated in ((info.get("subtitles") or {}, False),
                             (info.get("automatic_captions") or {}, True)):
        for lang, formats in store.items():
            # yt-dlp exposes machine translations alongside original captions.
            # Never request a translated URL, even if its language label matches.
            native = [f for f in formats if f.get("ext") == "json3" and f.get("url")
                      and "tlang" not in parse_qs(urlsplit(f["url"]).query, keep_blank_values=True)]
            if native and lang != "live_chat":
                tracks.append((_language(lang), generated, native))
    audio = [f for f in info.get("formats", [])
             if f.get("acodec") not in (None, "none") and f.get("language")]
    # yt-dlp marks the original audio with preference 10 (default/dubbed is 5).
    originals = [f["language"] for f in audio if f.get("language_preference") == 10]
    source = (_unique_language(originals) if originals else
              _unique_language(lang for lang, generated, _ in tracks if generated)
              or _unique_language(f["language"] for f in audio))
    if not source:
        return []
    return sorted((t for t in tracks if _base(t[0]) == source), key=lambda t: t[1])


def fetch(video_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        return {"error": "unavailable"}
    # This process receives only a video ID. No site token is passed to it.
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from requests import Session

        class TimedSession(Session):
            def request(self, *args, **kwargs):
                kwargs["timeout"] = 10
                return super().request(*args, **kwargs)

        with TimedSession() as session:
            tracks = list(YouTubeTranscriptApi(http_client=session).list(video_id))
            if not tracks:
                return {"error": "no_captions"}
            for candidate in api_source_tracks(tracks)[:4]:
                try:
                    track = candidate.fetch()
                    cues = [{"start": round(s.start, 3), "end": round(s.start+s.duration, 3),
                             "text": " ".join(s.text.split())} for s in track if s.text.strip()]
                    if cues:
                        return {"transcript": {"language": track.language_code, "is_generated": track.is_generated, "cues": cues}}
                except Exception:
                    # Try another track in the SAME language, never a translation.
                    continue
    except Exception:
        pass
    try:
        import yt_dlp

        class QuietLogger:
            def debug(self, *_args): pass
            def warning(self, *_args): pass
            def error(self, *_args): pass

        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True,
                              "socket_timeout": 10, "retries": 0, "extractor_retries": 0,
                              "logger": QuietLogger()}) as ydl:
            info = ydl.extract_info("https://www.youtube.com/watch?v=" + video_id, download=False)
            if not info or not (info.get("subtitles") or info.get("automatic_captions")):
                return {"error": "no_captions"}
            tracks = ytdlp_source_tracks(info)
            for lang, generated, formats in tracks[:4]:
                track = next((f for f in formats if f.get("ext") == "json3"), None)
                if not track:
                    continue
                try:
                    raw = ydl.urlopen(track["url"]).read(2_000_001)
                except Exception:
                    continue
                if len(raw) > 2_000_000:
                    return {"error": "fetch_failed"}
                cues = []
                for event in json.loads(raw).get("events", []):
                    words = " ".join("".join(s.get("utf8", "") for s in event.get("segs", [])).split())
                    if words:
                        start = event.get("tStartMs", 0) / 1000
                        cues.append({"start": start, "end": start+event.get("dDurationMs", 0)/1000, "text": words})
                if cues:
                    return {"transcript": {"language": lang, "is_generated": generated, "cues": cues}}
    except Exception:
        # Do not expose third-party responses/cookies to API logs.
        pass
    return {"error": "fetch_failed"}


if __name__ == "__main__":
    print(json.dumps(fetch(sys.argv[1]), ensure_ascii=True))
