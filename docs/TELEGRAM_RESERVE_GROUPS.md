# Telegram reserve-group operations

Reserve groups are private supergroups pre-created by a Xaana caretaker. They
are registered through the **running** `@xaana_bot`; never run another poller
with the production token. The bot is allowed to make ordinary outbound Bot
API calls from the web process while its single poller receives updates.

## Prepare each reserve

1. Create a private group named `C0002`, `C0003`, etc. Keep exactly two
   members: the caretaker human and `@xaana_bot`. No other bots, test users, or
   prior club conversations.
2. Make Xaana an admin with Change Info, Invite Users, Add New Admins, Delete
   Messages, and Ban Users. The group must be a supergroup.
3. Registration revokes the group's **primary** invite link for you: it calls
   `exportChatInviteLink`, which mints a fresh primary link and retires the
   previous one, then discards the new URL. That is the only way a bot can
   retire a link it did not create, and it neutralises every primary link
   handed out before registration.
   You still handle what the Bot API cannot see: **named** invite links created
   by other admins are not enumerable, so open *Manage Group -> Invite Links*
   and revoke any that are listed. Also check the group's history-visibility
   setting and remove setup messages that future members should not see.
4. From a Xaana admin account configured in `ADMIN_IDS`, privately message
   `@xaana_bot` with `/reserve_add C0002 -100... CLEAN`, substituting the
   group's numeric chat ID. The admin account need not be a group member or
   owner. `CLEAN` is an explicit attestation of steps 1–3. The bot verifies
   the actual group owner/caretaker, member count, and rights, then DMs the
   result. No registration message is posted to the group. `CLEAN` attests to
   the named-link and history checks in step 3; the primary link is handled
   automatically, and registration is refused outright if that revocation
   call fails.
5. Send `/reserve_list` privately to `@xaana_bot`, or check
   `GET /api/admin/clubs/reserves` as an authenticated Xaana admin. It
   lists labels, chat IDs, status, and attestation, never an invite URL. If a
   reserve is compromised, `POST /api/admin/clubs/reserves/{label}/disable`
   removes it from allocation. Re-registration after cleanup makes it
   available again.

The production `telegram_group_reserves` table is the authoritative inventory.
No dormant invite URL or bot token is stored there. The ignored local file
`scripts/telegram_reserve_group_probe/reserve_inventory.local.json` is a
provisional discovery note only; never commit secrets into it.

## Club allocation and handoff

When the Mini App creates a club, its web process atomically claims one
`available` reserve (`FOR UPDATE SKIP LOCKED`). It rechecks the group and admin
rights, renames the group to the requested club name, and mints a
`creates_join_request` link. Only then does it store the chat ID/link on the
club and mark the reserve `allocated`. The bot sends the creator this link.
If a Telegram or DB step fails, it revokes the new link, tries to restore the
old title, and quarantines the reserve as `needs_review`; the club stays in
the manual setup queue.

The running bot approves a join request only when its exact assigned link
matches and the requester is an active Xaana club member. It promotes the
club creator to group admin, then asks the caretaker to leave. The club stays
`ready` until Telegram confirms caretaker departure *and* the new admin role;
only then is it `connected`. An unknown member entering through some other
link is removed; an unexpected join while a group is still `available` also
quarantines that reserve. This mitigation is not a substitute for revoking old
links: a stale named link could still admit someone, and an unapproved join
could briefly view visible history before removal.
Xaana suppresses group welcomes, replies, and scheduled group reminders during
the `ready` handoff window; legacy non-reserve clubs keep their prior behavior.

Assigned groups are single-use, never returned to the pool. Archived clubs'
bot-created links are revoked best-effort; archive itself remains DB-only so
deletion does not depend on Telegram being reachable.
The web process alerts configured admins when one or zero available reserves
remain after allocation.

## Deployment order

1. Run offline tests and review the migration. Migration 039 adds only the
   reserve table; it does not touch existing clubs.
2. Apply migration 039 to **both production and staging DBs before** any code
   deploy. Staging's bot uses the staging DB, while the `zana-webapp` deployed
   by staging CI uses the production DB. Both are currently at revision 038.
3. Deploy the webapp and then the production bot under the normal release
   procedure. Verify one poller and healthy containers. Do not start another
   instance of `@xaana_bot` locally.
4. Register C0002–C0005 after the manual cleanup. Make a controlled club to
   consume C0002, check exact join-request approval, admin promotion, and
   caretaker departure before using the other reserves for real clubs.

## Known Telegram limitation

Telegram group ownership belongs to a human. The bot can promote a new admin
but cannot forcibly make the caretaker owner leave. The caretaker must leave
manually after the new admin joins; Telegram may transfer ownership later.
Until that leave event, the group is not considered fully handed off.
