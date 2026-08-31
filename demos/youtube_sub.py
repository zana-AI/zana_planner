from urllib.parse import urlparse, parse_qs
from youtube_transcript_api import YouTubeTranscriptApi


def get_video_id(url: str) -> str:
    parsed = urlparse(url)

    if parsed.hostname == "youtu.be":
        return parsed.path.lstrip("/")

    if parsed.path == "/watch":
        return parse_qs(parsed.query)["v"][0]

    if parsed.path.startswith("/shorts/"):
        return parsed.path.split("/")[2]

    raise ValueError("Unsupported YouTube URL")


def fetch_subtitles(url: str) -> dict:
    video_id = get_video_id(url)

    transcript = YouTubeTranscriptApi().fetch(
        video_id,
        languages=["en", "fr"],
    )

    segments = transcript.to_raw_data()

    return {
        "video_id": video_id,
        "language": transcript.language_code,
        "is_generated": transcript.is_generated,
        "text": " ".join(segment["text"] for segment in segments),
        "segments": segments,
    }

VIDEO_ID = "https://www.youtube.com/watch?v=HLNcOuiZ_Zk"

# result = fetch_subtitles("https://www.youtube.com/watch?v=VIDEO_ID")
result = fetch_subtitles(VIDEO_ID)
print(result["text"])