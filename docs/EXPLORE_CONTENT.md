# Explore content

Explore is rendered from the curated `explore_catalog` row in PostgreSQL. The
catalog is content data: it is not bundled into the webapp image or committed to
the code repository. The `content` table holds video records and their access
policy; the catalog controls which items are discoverable.

The loader refreshes at most once per minute, validates the document, removes
unpublished categories/topics/items, and sorts each level by `order` (then by
`id`). If the database is temporarily unavailable or a refreshed document is
invalid, the last known good catalog remains available in that webapp process.
An unseeded database returns an empty Explore view.

For editorial changes, export the database catalog to a file outside the
repository, edit it, then import with the SHA-256 printed by export. Import
refuses concurrent changes and requires any newly listed video to already have
a public `content` row:

```bash
python scripts/manage_explore_catalog.py export --output /tmp/explore.yaml
python scripts/manage_explore_catalog.py import --file /tmp/explore.yaml --expected-sha256 YOUR_EXPORTED_HASH
```

The language publisher accepts an external `--batch` file and updates both the
public `content` rows and the curated catalog in one database transaction:

```bash
python scripts/publish_language_catalog.py --batch /path/to/language-batch.yaml
python scripts/publish_language_catalog.py --batch /path/to/language-batch.yaml --apply
```

The first command writes a preview under `exports/` without publishing. The
second requires recent verification and never changes an existing private or
club-only content row to public. Both commands run in the webapp's configured
database environment. The first deployment of this storage model uses
`scripts/seed_explore_catalog.py --file <current-live-explore.yaml> --apply`
after migration `043_explore_catalog`; the seed command refuses to overwrite an
existing catalog.

To prepare another language batch, export the current catalog and pass that
export plus an external source-rules file to the builder. Keep the resulting
manifest outside Git as well:

```bash
python scripts/build_language_catalog.py --sources /path/to/language-sources.yaml \
  --catalog /tmp/explore.yaml --output /tmp/language-batch.yaml --verify
```

## Organised by subject

**A category is a subject — something a person is working on.** French,
English, Body, Care. A topic is the *kind* of thing inside that subject:
a quiz, a club, a habit.

This is deliberately not the other way round. "A French quiz" is not a
top-level thing; it belongs under French, next to the French videos and the
French decks, because someone learning French wants them in one place. A new
kind of content becomes a new topic inside the subjects that have it — never a
new tab.

## Topic ids are a fixed vocabulary

A topic id is not free text. It comes from this list, and the `order` that goes
with it, so that the same five words mean the same thing in every subject and
the client can render them as filter chips without special-casing a category:

| Topic | order | Holds | The action |
|---|---|---|---|
| `courses` | 10 | challenges with a coach and a cadence | Join |
| `watch` | 20 | videos with subtitles | Watch |
| `read` | 30 | books, PDFs, articles | Read |
| `decks` | 40 | self-paced card sets | Study |
| `habits` | 50 | promise templates | Promise it |

**A course is a deck that a person releases on a cadence, with a leaderboard
attached.** Anything self-paced is a deck, whatever serves its content: French
Naturalization Prep sits under `decks` even though the challenge engine holds
its questions, because nobody releases it. A deck can become a course later by
gaining a coach and a cadence, with no new object.

## A club is never listed here

A club and its challenge are the same entity at two time scales
(`docs/CLUBS_MODEL.md` §3). Listing both put "French with Atena" in Explore
twice, once as a quiz and once as a club, which is the confusion this vocabulary
exists to prevent. Coach-led clubs appear once, under `courses`, in their
subject. Peer clubs — a couple going to the gym, six friends — do not appear in
Explore at all; they live in Community.

## It is an allowlist, not a mirror

Nothing reaches Explore unless it is included in the curated catalog. There is no job
that syncs the catalog from the database, and there should not be — the
database holds test fixtures, archived rows and half-finished content that must
never surface. Curation *is* the feature.

The Library Share menu is an explicit publishing path for a saved YouTube video
or an owned PDF (including a public PDF saved by someone else).
`POST /api/content/{id}/share` with `destination=explore`
checks the caller's Library access, checks the catalog for the same content or
YouTube video ID, then makes the content public and inserts a card in one
transaction. It does not re-publish an item hidden by a curator. Sharing only
the Xaana link makes the content public without adding it to Explore. The
share sheet states that other Xaana users can then open the PDF.
When someone saves a video already listed in the published catalog, the save
route also repairs a legacy private YouTube content row before adding it to
their Library. Hidden or club-only content is never promoted this way.

Existing descriptions such as `A2-B1 estimate. …` are split at response time:
the level appears as a metadata badge and the remaining text as the card
description. No editorial content is rewritten in the catalog by that display
change. New shares can supply an explicit language and CEFR level.

Only globally-valid destinations belong in the catalog:

- **challenges** — `visibility=public`, `status=active`
- **promise templates** — `is_active=1`
- **videos and other content** — the `content` row must be
  `visibility='public'`, not merely listed here

## Listing something is not the same as sharing it

Two independent mechanisms, and a content item needs both:

| | What it does | Where it lives |
|---|---|---|
| This catalog | makes an item *appear* in Explore | `explore_catalog.document` |
| `content.visibility` | decides who may *save or open* it | the `content` table |

`content.visibility` defaults to `'private'`, and `can_access_content` admits
only the owner, someone who already holds the item, a member of its club — or
anyone at all once it is `'public'`. `POST /user-content` enforces that with a
403, *"This content is not shared with you"*.

So a video listed here whose row is private is half-published: the watch page
opens, because `/youtube-watch` is a public page that never consults the
content row, but **＋ Add fails for everyone except the owner**. The card looks
right up to the moment somebody taps the button.

When you list a content item, make its row public in the same transaction.

**Never list per-user rows.** A `flashcard_deck` belongs to a single `user_id`,
so putting one in the catalog would show every user a link into someone else's
deck. Your own decks are not discovery — they live in Library.

## Document schema

```yaml
version: 1
categories:
  - id: french
    title: French
    icon: bubble-fr
    accent: "#22D3EE"
    order: 10
    published: true
    topics:
      - id: courses
        title: Courses
        order: 10
        published: true
        items:
          - id: atena-fr
            title: French with Atena 🇫🇷
            type: challenge
            order: 10
            published: true
            description: A short daily French quiz — 10 new questions every day.
            native_ref: /challenges/660762b526d849ffa4470a9e690fc2d3
      - id: watch
        title: Watch
        order: 20
        published: true
        items:
          - id: sample-video
            title: Sample video
            type: video
            order: 10
            published: true
            description: A sample entry illustrating the document shape.
            image: https://img.youtube.com/vi/abcdefghijk/mqdefault.jpg
            native_ref: /youtube-watch?video_id=abcdefghijk
```

Each item uses `url` for an external destination or `native_ref` for an
application route. The client follows an `http(s)` `url` or a `native_ref`
beginning with `/`, and disables the card otherwise, so a malformed entry
cannot become a `javascript:` navigation.

`type` is intentionally free-form so new item types can be introduced as
content evolves; the current client displays the shared title, description,
image metadata, and optional class offer for every type.

`icon` and `accent` are optional category display fields.
