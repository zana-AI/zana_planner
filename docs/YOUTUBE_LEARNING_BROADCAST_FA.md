# YouTube learning announcement — approved Persian campaign

Status: **APPROVED — deployment and scheduling requested; not yet scheduled or sent.** Prepared 2026-09-24.

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
- Use the existing admin broadcast scheduler, not a separate cron or Codex reminder. Set `source_language=fa`, `translate_to_user_language=false` so approved Persian is not machine-rewritten.
- No message or pending broadcast record was created. Current production pending-broadcast count: zero at the check.
- Before scheduling, deploy and verify the accompanying bot/viewer labels so the instructions match what users actually see. The earlier redesign commit `fddcfc6` was still local at this check (production bot `47b3125`, new discovery backend absent).
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
