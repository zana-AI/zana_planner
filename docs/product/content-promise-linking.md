# Content to Promise Linking

## Status

Decision note, first draft.

## Context

Zana already has two important concepts:

- **Promise**: the accountable unit. A user commits to doing something within a time period.
- **Content**: material a user may read, watch, listen to, highlight, summarize, quiz on, or ask questions about.

We want content consumption to become part of the promise system without forcing every saved content item to be immediately planned.

## Decision

Content can exist in two broad modes:

1. **Unplanned content**
   - Content saved in the user's library.
   - It is not yet part of an accountable commitment.
   - It can be read, watched, highlighted, or kept for later.

2. **Promise-linked content**
   - Content attached to one or more promises.
   - It becomes part of the user's accountability flow.
   - Progress, check-ins, reminders, and weekly views can use this relationship.

The core rule is:

> Content may exist without a promise while it is unplanned. Once content becomes accountable or scheduled, it should be linked to a promise.

## Domain relationship

```text
User
  -> has Promises
  -> has saved Content

Promise
  -> may link to zero, one, or many Content items

Content
  -> may be unplanned
  -> may be linked to one or many Promises
```

A many-to-many relation is expected between promises and content:

```text
promise_content_links
  - promise_uuid
  - content_id
  - created_at_utc
  - created_by_user_id
  - optional role: primary | supporting | reference
  - optional position/order
```

## UX implications

### My Week / Today view

When listing active promises for the current period, if a promise has linked content, the mini app should make that content accessible from the promise card.

Possible UI behaviors:

- show a small content icon on the promise badge/card
- open linked content list when tapping the promise card
- allow quick navigation to the PDF/content reader page

### Content reader / content detail page

When a user opens content that is still unplanned, the mini app can later suggest:

> Do you want to connect this content to one of your promises?

This prompt is not required for the first implementation, but the data model should support it.

### Promise detail page

A promise detail page should eventually show:

- linked content items
- reading/watching progress per item
- highlights or notes, if relevant
- quick action to add or remove content links

## Out of scope for now

The following are intentionally not part of this decision:

- Programs as a separate grouping layer
- Sub-promises
- Complex group reading milestones
- Advanced nudging logic
- Full collaborative annotation

## Product principle

Promise remains the central accountability unit.

Content is the material. It becomes meaningful for Zana's promise system when it is linked to a promise.
