# Explore content

Explore is rendered from a small YAML catalog. Set `EXPLORE_CONFIG_URL` in the
webapp environment to a raw, publicly readable `explore.yaml` that the owner
can update without rebuilding the application. When the URL is absent or
unavailable, the bundled `tm_bot/config/explore.yaml` is used.

The loader refreshes at most once per minute, validates the document, removes
unpublished categories/topics/items, and sorts each level by `order` (then by
`id`). If a refreshed document is invalid, the last known good catalog remains
available.

```yaml
version: 1
categories:
  - id: learning
    title: Learning
    order: 10
    published: true
    topics:
      - id: languages
        title: Languages
        order: 10
        published: true
        items:
          - id: french-classes
            title: French classes
            type: offer
            order: 10
            published: true
            description: Practice with a friendly teacher.
            class_offer: "French classes — €5/hour"
            native_ref: /templates
          - id: french-channel
            title: Learn French on Telegram
            type: telegram
            order: 20
            published: true
            url: https://t.me/example
            image: https://example.com/cover.jpg
```

Each item may use `url` for an external destination or `native_ref` for an
application route. `type` is intentionally free-form so new item types can be
introduced as content evolves; the current client displays the shared title,
description, image metadata, and optional class offer for every type.
