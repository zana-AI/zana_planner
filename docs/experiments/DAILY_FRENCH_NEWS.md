# Daily French news candidate pipeline

The [script](../../scripts/daily_french_news_candidates.py) builds a **review queue**; it never inserts content into Xaana. It runs daily on the Xaana VM at 10:15 Europe/Paris, after YouTube's Pacific-time quota reset. The output is `/opt/zana-config/news-discovery/reports/latest.md` and `latest.json`, plus date-stamped copies.

## How it works

1. Read fresh Google Trends RSS searches for France, the US, and the UK, and French-language article headlines from RFI, France 24, and franceinfo. Each headline retains its source link and publication time. A missing secondary feed is reported without discarding the whole run; the France trends feed and at least one news feed are required.
2. Ask Groq's `openai/gpt-oss-20b` for a bounded set of distinct France and world stories. The prompt gets the live data, and code rejects headline search phrases that add words not present in the cited headline. If topic selection fails, the run fails rather than producing a traffic-only list.
3. Search YouTube Data API for each story in French, using its `publishedAfter`, `regionCode`, `relevanceLanguage`, embeddability, and duration filters. At most three searches are made per topic, or 42 at the default topic limits. Batch-fetch video details once per 50 IDs.
4. Reject videos already in Xaana, unavailable videos, declared non-French audio, videos older than 72 hours, and videos uploaded more than 24 hours before the story headline. Rank by topic match, recency, caption flag, and publisher signal. Limit repetition by topic and channel.

The YouTube caption flag is **not** a transcript test. A human should check the video and transcript before importing. The report may contain fewer than twelve links, including none for a scope, when there are no credible recent matches.

## Run and inspect

On the VM:

```bash
systemctl status xaana-french-news-discovery.timer
systemctl start xaana-french-news-discovery.service
cat /opt/zana-config/news-discovery/reports/latest.md
journalctl -u xaana-french-news-discovery.service -n 30 --no-pager
```

The YouTube key is restricted to the VM's outbound IP addresses and the YouTube Data API, stored separately at `/opt/zana-config/youtube_news_discovery.key` with mode `600`. The script reads only `GROQ_API_KEY` from the existing private production environment file. No keys are placed in reports or the repository.

The YouTube API currently has a separate default allowance of 100 `search.list` requests daily, subject to the project's configured quota. Today's exploratory calls exhausted that bucket; the first scheduled report is due after the reset. See [YouTube Search API](https://developers.google.com/youtube/v3/docs/search/list), [quota overview](https://developers.google.com/youtube/v3/getting-started), and [Google Trends RSS guidance](https://support.google.com/trends/answer/3076011?hl=en).
