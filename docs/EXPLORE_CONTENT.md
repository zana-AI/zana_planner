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

**A category is a subject — something a person is working on.** French, Gym &
Exercise, Care, English. A topic is the *kind* of thing inside that subject:
a quiz, a club, a habit.

This is deliberately not the other way round. "A French quiz" is not a
top-level thing; it belongs under French, next to the French clubs and the
French habits, because someone learning French wants them in one place. A new
kind of content becomes a new topic inside the subjects that have it — never a
new tab.

Each topic maps to one thing a person can do, so a row needs only one verb:

| Topic | Holds | The action |
|---|---|---|
| Daily quiz | challenges | Join, or Continue once joined |
| Review | flashcard decks | Review |
| Watch & read | content items | Watch / Read |
| Clubs | clubs | Join |
| Habits | promise templates | Promise it |

## It is an allowlist, not a mirror

Nothing reaches Explore unless it is written down in the YAML. There is no job
that syncs the catalog from the database, and there should not be — the
database holds test fixtures, archived rows and half-finished content that must
never surface. Curation *is* the feature.

Only globally-valid destinations belong in the catalog:

- **challenges** — `visibility=public`, `status=active`
- **clubs** — public clubs only. `/c/<club_id>` returns 404 to anyone who is not
  a member of a private club, so listing one produces a dead link.
- **promise templates** — `is_active=1`

**Never list per-user rows.** A `flashcard_deck` belongs to a single `user_id`,
so putting one in the catalog would show every user a link into someone else's
deck. The Explore page already lists the caller's own decks from its own
endpoint.

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
      - id: quizzes
        title: Daily quiz
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
          - id: french-channel
            title: Learn French on Telegram
            type: telegram
            order: 20
            published: true
            url: https://t.me/example
            image: https://example.com/cover.jpg
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
