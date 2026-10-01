"""YouTube metadata used by new Library saves and one-time backfills."""
from utils import youtube_utils


def test_youtube_iso_duration_including_days():
    assert youtube_utils.parse_youtube_duration('PT5M31S') == 331
    assert youtube_utils.parse_youtube_duration('P1DT2H3M4S') == 93784
    assert youtube_utils.parse_youtube_duration('P2W') is None


def test_youtube_api_enriches_missing_library_fields(monkeypatch):
    class Response:
        status_code = 200

        def json(self):
            return {'items': [{'snippet': {
                'defaultAudioLanguage': 'fr-FR', 'publishedAt': '2026-09-30T08:00:00Z',
                'description': 'A useful video',
            }, 'contentDetails': {'duration': 'PT5M31S'}}]}

    monkeypatch.setattr(youtube_utils.requests, 'get', lambda *_args, **_kwargs: Response())
    result = {'language': None, 'duration_seconds': None, 'duration_formatted': 'Unknown',
              'published_at': None, 'description_snippet': None, 'category': None}
    youtube_utils._enrich_with_youtube_api('abcdefghijk', result, 'test-key')
    assert result['language'] == 'fr-FR'
    assert result['published_at'] == '2026-09-30T08:00:00Z'
    assert result['duration_seconds'] == 331
    assert result['description_snippet'] == 'A useful video'
