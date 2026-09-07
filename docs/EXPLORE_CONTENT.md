# Explore content

Explore is rendered from a small YAML catalog. Set `EXPLORE_CONFIG_URL` in the
webapp environment to a raw, publicly readable `explore.yaml` that the owner
can update without rebuilding the application. When the URL is absent or
unavailable, the bundled `tm_bot/config/explore.yaml` is used.

The loader refreshes at most once per minute, validates the document, removes
unpublished categories/topics/items, and sorts each level by `order` (then by
`id`). If a refreshed document is invalid, the last known good catalog remains
available.

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

Nothing reaches Explore unless it is written down in the YAML. There is no job
that syncs the catalog from the database, and there should not be — the
database holds test fixtures, archived rows and half-finished content that must
never surface. Curation *is* the feature.

Only globally-valid destinations belong in the catalog:

- **challenges** — `visibility=public`, `status=active`
- **promise templates** — `is_active=1`

**Never list per-user rows.** A `flashcard_deck` belongs to a single `user_id`,
so putting one in the catalog would show every user a link into someone else's
deck. Your own decks are not discovery — they live in Library.

## Schema

```yaml
version: 1
categories:
  - id: french
    title: French
    icon: bubble-fr        # not read yet — see below
    accent: "#22D3EE"      # not read yet — see below
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
          - id: video-sud-radio
            title: "Olivier : ..."
            type: video
            order: 10
            published: true
            description: French subtitles — tap a word to translate and save a card.
            image: https://img.youtube.com/vi/c4dtEcHyNcc/mqdefault.jpg
            native_ref: /youtube-watch?video_id=c4dtEcHyNcc
```

Each item uses `url` for an external destination or `native_ref` for an
application route. The client follows an `http(s)` `url` or a `native_ref`
beginning with `/`, and disables the card otherwise, so a malformed entry
cannot become a `javascript:` navigation.

`type` is intentionally free-form so new item types can be introduced as
content evolves; the current client displays the shared title, description,
image metadata, and optional class offer for every type.

`icon` and `accent` on a category are **read by nothing today** — the pydantic
models ignore unknown keys. They are written in the catalog so the tile design
has its data ready when `ExploreCategory` gains the fields.
