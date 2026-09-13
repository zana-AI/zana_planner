# Reserved Telegram group probe

This is an isolated capability test for the reserve-group model. It proves that
a bot already made an administrator in a pre-created Telegram group can:

1. discover the group numeric chat ID;
2. verify its own invite permission;
3. mint a short-lived, one-person invite link; and
4. deliver that link privately to the group member who requested it.

It does **not** change Xaana's production database or link this test group to a
club.

## Run

1. Copy `.env.example` to `.env` in this directory and set `RESERVE_BOT_TOKEN`
   to the token for `@Javad_bot_test_bot`. The repository ignores `.env` files.
2. From the repository root in WSL's `zana_planner` Conda environment, run:

   ```bash
   conda activate zana_planner
   python scripts/telegram_reserve_group_probe/probe_reserve_group.py
   ```

3. Before (or while) it is waiting, open a private chat with
   `@Javad_bot_test_bot` and press **Start**. Telegram otherwise does not allow
   a bot to message you privately.
4. In the reserved test group, send `/reserve_test` as a standalone message.
   Do not rely on a normal message: Telegram privacy mode can hide ordinary
   group text from the bot.

To check that the bot can change a reserved group's name and inspect its admin
permissions, run the following after discovering the numeric group ID:

```bash
python scripts/telegram_reserve_group_probe/probe_reserve_group.py --chat-id GROUP_ID
```

The script temporarily names the group `Xaana reserve group probe`, verifies
the change, and restores its previous title. It prints whether the bot may
change group info, invite members, promote members, restrict members, delete
messages, and pin messages. It does not change member roles.

On success, the terminal prints the numeric chat ID and permission result. The
test bot sends the temporary, single-use invite link directly to the account
that issued `/reserve_test`; the script deliberately does not log the link.

The generated link expires in 15 minutes and admits one member. It can be
revoked from Telegram's group invite-link controls if the test is stopped early.

## Live handoff test

For a known, pre-created supergroup, run:

```bash
python -u scripts/telegram_reserve_group_probe/probe_reserve_group.py --handoff --chat-id GROUP_ID
```

The terminal prints a new 15-minute, one-person invite and a random claim
command. From the intended second account, send the claim command privately to
the test bot and join through that **new** link. The script promotes only the
account that both claimed privately and was observed joining through that exact
link. It checks the Telegram admin role after promotion, then revokes the
temporary invite. It does not promote the first account or anyone who only
obtains the link. Wait for `PASS` before the first account leaves the group.

After leaving, check the remaining administrators without changing the group:

```bash
python scripts/telegram_reserve_group_probe/probe_reserve_group.py --audit --chat-id GROUP_ID
```

This is a manual capability test, not a production club-allocation workflow.
