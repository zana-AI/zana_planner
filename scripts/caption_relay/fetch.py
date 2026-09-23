"""Bounded subprocess entry point, shared by cloud and residential workers."""
import json
import re
import sys


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
            tracks.sort(key=lambda t: (t.language_code.split("-")[0] not in ("fr", "en"), t.is_generated))
            if not tracks:
                return {"error": "no_captions"}
            track = tracks[0].fetch()
            cues = [{"start": round(s.start, 3), "end": round(s.start+s.duration, 3),
                     "text": " ".join(s.text.split())} for s in track if s.text.strip()]
            if cues:
                return {"transcript": {"language": track.language_code, "is_generated": track.is_generated, "cues": cues}}
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
            tracks = [(lang, generated, formats)
                      for store, generated in ((info.get("subtitles") or {}, False),
                                               (info.get("automatic_captions") or {}, True))
                      for lang, formats in store.items()]
            tracks.sort(key=lambda t: (t[0].split("-")[0] not in ("fr", "en"), t[1]))
            if not tracks:
                return {"error": "no_captions"}
            for lang, generated, formats in tracks[:4]:
                track = next((f for f in formats if f.get("ext") == "json3"), None)
                if not track:
                    continue
                raw = ydl.urlopen(track["url"]).read(2_000_001)
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
