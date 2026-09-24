# YouTube learning announcement — approved Persian campaign

Status: **SCHEDULED — pending, not sent yet.** Verified 2026-09-24 11:52 UTC.

- Production release: `856e793c2a9b0db858f8f7146519c3e7f3d16407` (web app and bot), health verified.
- Staging/webapp workflow: https://github.com/zana-AI/zana_planner/actions/runs/35995085243
- Production promotion: https://github.com/zana-AI/zana_planner/actions/runs/35995405003
- Broadcast ID: `a61c1edb-701d-400c-a3a2-f35f6f6f7e05` in the production broadcast scheduler.
- Delivery: 2026-09-24 17:00 UTC / 19:00 Paris / 20:30 Tehran, via `@xaana_bot`.
- Recipient snapshot: 193 registered private-chat IDs; 57 named greetings and 136 plain greetings at setup. Names are resolved again at send time. No recipient IDs or names are stored in this document.
- Approved template SHA-256 (UTF-8, LF): `3061614d5cbdd8a4acac1419601dd0c82224e0020385150129c69e38d70a0ca1`.
- Exactly one matching campaign; future timestamp and pending status read back after creation. No immediate message was sent.

## Approved message template

```text
{{greeting_fa}} 👋

یه قابلیت جدید به زانا اضافه شده که برای یادگیری زبان خیلی به کار میاد.

می‌تونی لینک یه ویدیوی دلخواهت از یوتیوب رو همین‌جا بفرستی و به «کتابخانه» اضافه‌اش کنی.

بعد، توی اپ زانا ویدیو رو با زیرنویس تعاملی ببین، روی کلمه‌هایی که بلد نیستی بزن تا معنی‌شون رو ببینی، و هر کدوم رو خواستی به‌صورت فلش‌کارت ذخیره کن تا بعداً مرورش کنی.

برای شروع، فقط کافیه لینک یه ویدیوی یوتیوب رو همین‌جا بفرستی 🙂
اگه جایی به کمک نیاز داشتی، بهم بگو.
```

`{{greeting_fa}}` becomes `سلام <first_name>!`, or `سلام!` when no name is recorded. Recipient names are escaped for Telegram Markdown. No placeholder is sent literally.

## Delivery plan

- One Persian text message to all eligible registered private-chat users of the production Xaana bot; 193 positive numeric user IDs at the read-only check. This is not a promise that all users are reachable: blocked/deleted chats can fail delivery.
- Scheduled target: 2026-09-24 20:30 Asia/Tehran = 19:00 Europe/Paris = 17:00 UTC, using the previously proposed evening time. Never silently shift a past time to the next day.
- Scheduled through `BroadcastsRepository`, the same backend used by the Admin scheduler, with the unchanged approved Persian message. No translation step, separate cron, or Codex reminder. The production webapp dispatcher checks due broadcasts every 15 seconds.
- The bot/viewer wording and new design were deployed and verified before creating the pending record. All six curated videos have cached original-language subtitles and verified duration metadata.
- User approved the final copy and requested deployment plus broadcast setup. Snapshot recipient IDs in the broadcast record, check for an existing matching campaign to avoid duplicates, and read back scheduled UTC time and recipients. Do not send an extra test message to all users.
- Do not put user-specific session tokens in a shared broadcast. The deliberately simple call to action is to send a YouTube link in the same chat; no new login or deep-link routing is needed.

## Lightweight measurement plan

No new analytics collection or database migration for this first campaign.

- Freeze the recipient cohort and send timestamp at approval/scheduling.
- Compare the preceding 48 hours with the following 48 hours for recipient users with recorded YouTube watching (`content_consumption_event`, joined to YouTube content), and new YouTube flashcard notes (`flashcard_note.source='youtube'`, `created_at`). Count unique users as well as videos/notes, not repeated progress pings.
- Existing send code reports Telegram API successes/failures in logs; the broadcast table stores status, not recipient-level delivery, opens or clicks. `completed` alone does not mean every recipient received/read it.
- This measures activity after the announcement, not causal campaign conversion or message opens. A tagged-link attribution feature would be separate work.
- No follow-up automation is configured yet; agree on reporting after the send is approved.

## Copy direction

Use conversational Iranian Persian for guidance: رو، می‌تونی، بفرست، بزن.
Keep action labels short and predictable: کتابخانه، تماشای ویدیو، ذخیره کارت، مرور.
Avoid literal UI translations such as «پیوند را بچسبانید»، «منوی نمایه» or «کتابخانه گسترده‌تر شود».
Keep video titles/channel names in their original language. Do not promise subtitles for every video.
