# Telegram reserve-group operations

Reserve groups are private supergroups pre-created by a Xaana operator, who
then leaves. A reserve in the pool contains **only `@xaana_bot`**. They are
registered through the **running** `@xaana_bot`; never run another poller with
the production token. The bot is allowed to make ordinary outbound Bot API
calls from the web process while its single poller receives updates.

Telegram keeps a bot's admin rights intact in an ownerless supergroup —
verified against a live group, including `can_promote_members`. That is what
makes a bot-only reserve work: the club creator is promoted on join and there
is nobody to hand off from.

## Prepare each reserve

1. Create a private group named `C0002`, `C0003`, etc. No other bots, test
   users, or prior club conversations.
2. Make Xaana an admin with Change Info, Invite Users, Add New Admins, Delete
   Messages, and Ban Users. The group must be a supergroup.
3. Check the group's history-visibility setting, remove setup messages future
   members should not see, and open *Manage Group -> Invite Links* to revoke
   any **named** links. Named links made by other admins cannot be enumerated
   over the Bot API, so this part is yours. The **primary** link is handled for
   you at registration: it calls `exportChatInviteLink`, which mints a fresh
   primary link and retires the previous one, then discards the new URL. That
   is the only way a bot can retire a link it did not create.
4. **Leave the group.** Registration requires exactly one member, the bot.
   Note that Telegram's `creator` status is unrecoverable — once you leave you
   can be re-added as an admin but never as owner again. That is fine here, and
   is the same end state the group would reach anyway.
5. From a Xaana admin account configured in `ADMIN_IDS`, privately message
   `@xaana_bot` with `/reserve_add C0002 -100... CLEAN`, substituting the
   group's numeric chat ID. The admin account is not a group member. The bot
   verifies the group is a bot-only supergroup with the required rights, then
   DMs the result. No registration message is posted to the group. `CLEAN`
   attests to the named-link and history checks in step 3; registration is
   refused outright if the primary-link revocation fails.
6. Send `/reserve_list` privately to `@xaana_bot`, or check
   `GET /api/admin/clubs/reserves` as an authenticated Xaana admin. It
   lists labels, chat IDs, status, and attestation, never an invite URL. If a
   reserve is compromised, `POST /api/admin/clubs/reserves/{label}/disable`
   removes it from allocation. Re-registration after cleanup makes it
   available again.

The production `telegram_group_reserves` table is the authoritative inventory.
No dormant invite URL or bot token is stored there. The ignored local file
`scripts/telegram_reserve_group_probe/reserve_inventory.local.json` is a
provisional discovery note only; never commit secrets into it.

## Club allocation

When the Mini App creates a club, its web process atomically claims one
`available` reserve (`FOR UPDATE SKIP LOCKED`). It rechecks the group and admin
rights, renames the group to the requested club name, and mints a
`creates_join_request` link. Only then does it store the chat ID/link on the
club and mark the reserve `allocated`. The bot sends the creator this link.
If a Telegram or DB step fails, it revokes the new link, tries to restore the
old title, and quarantines the reserve as `needs_review`; the club stays in
the manual setup queue.

The running bot approves a join request only when its exact assigned link
matches and the requester is an active Xaana club member. It promotes the club
creator to group admin and marks the club `connected` in the same step — with
no human in the group, there is no departure to wait for. If Telegram does not
confirm the promotion, the club stays `ready` and admins are alerted rather
than the club being reported as done.

An unknown member entering through some other link is removed; an unexpected
join while a group is still `available` also quarantines that reserve. This
mitigation is not a substitute for revoking old links: a stale named link could
still admit someone, and an unapproved join could briefly view visible history
before removal.

Assigned groups are single-use, never returned to the pool. Archived clubs'
bot-created links are revoked best-effort; archive itself remains DB-only so
deletion does not depend on Telegram being reachable.
The web process alerts configured admins when one or zero available reserves
remain after allocation.

## Deployment order

1. Run offline tests and review the migration. Migration 039 adds only the
   reserve table; 040 drops its `caretaker_user_id` column. Neither touches
   existing clubs.
2. Apply migrations to **both production and staging DBs before** any code
   deploy. Staging's bot uses the staging DB, while the `zana-webapp` deployed
   by staging CI uses the production DB.
3. Deploy the webapp and then the production bot under the normal release
   procedure. Verify one poller and healthy containers. Do not start another
   instance of `@xaana_bot` locally.
4. Register the reserves after the manual cleanup. Make a controlled club to
   consume one, and check exact join-request approval and admin promotion
   before using the other reserves for real clubs.

## Consequences of the bot-only model

The club group ends up with the creator as **admin**, not owner, and no owner
at all. Telegram has no way for a bot to grant ownership. Practically this
means nobody can delete the group outright or use owner-only settings; the
creator can still manage members, pin, and change info. The earlier
caretaker-based design reached the same ownerless end state, just after an
extra departure step.
