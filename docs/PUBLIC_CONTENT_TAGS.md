# Public content topic tags

Public content can carry up to three canonical topic IDs in
`content.metadata_json.tags`. Explore entries carry the same `tags` for non-video
cards and the cached catalog; public video metadata takes precedence at runtime.
Language, CEFR level and content format are separate fields.

The taxonomy is defined in `tm_bot/services/content_tags.py`: news (actualité),
science, sport, technology, culture, economy, politics, society, health, travel,
nature, food and language_learning. Unknown topics remain untagged. These IDs
can later be used for explicitly chosen onboarding interests; do not infer a
user's interests from publishing tags or change their preferences during tagging.

`scripts/tag_public_content.py --propose /tmp/content-tags.json` produces topic
proposals from public titles and descriptions, including published catalog items
without a content row yet, using the configured Groq account.
It does not write to the database. Review the proposed tags and reasons first,
then use `--apply-reviewed /tmp/content-tags.json`. Applying locks and updates
public content and the Explore catalog in one transaction, preserving other
metadata and visibility, and writes backups alongside the reviewed file.
Provider metadata refreshes merge fields so they do not erase editorial tags.

New publishing pipelines should supply these tags as metadata. Library shares
inherit existing tags. Daily news publications use `news` plus the actual
subjects; article matching and subject classification are separate decisions.
