"""Safety gates for the daily French news review queue."""

from datetime import datetime, timezone
import json
import unittest
from unittest.mock import patch

from scripts import daily_french_news_candidates as news


NOW = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)


class DailyFrenchNewsSafetyTests(unittest.TestCase):
    def test_video_must_be_fresh_relative_to_story_not_just_today(self):
        topic = {
            "trend_id": "NEWS:one", "french_query": "Budget 2027 gouvernement",
            "scope": "france", "lead_published_at": "2026-10-01T09:00:00+00:00",
        }

        def candidate(identifier, published_at):
            return {
                "id": identifier, "title": "Budget 2027 : le gouvernement présente ses mesures",
                "description": "Budget 2027 en France", "channel": "FRANCE 24",
                "channel_id": "france24", "published_at": published_at,
                "language": "fr", "duration_seconds": 600, "captions_reported": True,
                "privacy": "public", "embeddable": True, "topic": topic, "search_rank": 0,
            }

        selected, excluded, _ = news.rank_videos(
            [candidate("abcdefghijk", "2026-09-30T08:00:00Z"),
             candidate("lmnopqrstuv", "2026-09-30T12:00:00Z")],
            set(), NOW, 72, 10,
        )

        self.assertEqual([item["id"] for item in selected], ["lmnopqrstuv"])
        self.assertEqual(excluded, {"older_than_story": 1})

    def test_topic_filter_cannot_add_an_event_absent_from_headline(self):
        headline = {
            "id": "NEWS:budget", "kind": "news", "region": "NEWS",
            "title": "Budget 2027 : le gouvernement présente ses mesures",
            "source_name": "France 24", "traffic": 0,
            "published_at": "2026-10-01T09:00:00+00:00",
        }
        response = {"choices": [{"message": {"content": json.dumps({"topics": [{
            "trend_id": "NEWS:budget", "french_query": "Budget 2027 crise nucléaire",
            "category": "economy", "scope": "france",
        }]})}}]}
        with patch.object(news, "http_json", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "no trustworthy trends"):
                news.choose_topics([headline], "fake-test-key", 8, 6)

    def test_related_headlines_do_not_create_two_searches_for_one_story(self):
        headlines = [
            {"id": "NEWS:blocage", "kind": "news", "region": "NEWS",
             "title": "Blocage des lycées en France", "source_name": "RFI",
             "traffic": 0, "published_at": "2026-10-01T09:00:00+00:00"},
            {"id": "NEWS:blocus", "kind": "news", "region": "NEWS",
             "title": "Blocus des lycées en France", "source_name": "France 24",
             "traffic": 0, "published_at": "2026-10-01T09:00:00+00:00"},
        ]
        response = {"choices": [{"message": {"content": json.dumps({"topics": [
            {"trend_id": "NEWS:blocage", "french_query": "Blocage des lycées France",
             "category": "public_affairs", "scope": "france"},
            {"trend_id": "NEWS:blocus", "french_query": "Blocus des lycées France",
             "category": "public_affairs", "scope": "france"},
        ]})}}]}
        with patch.object(news, "http_json", return_value=response):
            selected, _ = news.choose_topics(headlines, "fake-test-key", 8, 6)
        self.assertEqual([item["trend_id"] for item in selected], ["NEWS:blocage"])
