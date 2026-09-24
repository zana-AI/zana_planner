# Browser account switching

The legacy Telegram widget remembers its own account in cross-origin cookies.
Xaana logout cannot clear those cookies, and its public API has no documented
account chooser. Keep the normal widget, with a **Use another Telegram account**
alternative beside it on the sign-in screen. The everyday profile menu keeps
Logout for browser sessions; switching accounts is not a primary app action.

1. Visit `/login`. Switch to the desired account in the Telegram client.
2. Send `/login` privately to the Xaana bot (or use `?start=browser_login`).
3. Open the returned link in the desired browser, or paste it on `/login`.
4. Check the account name, username and Telegram ID; explicitly confirm.

The old browser account remains intact until confirmation succeeds. A full
navigation clears account-specific UI state; other SPA tabs reload on the token
storage event. The standalone video viewer also leaves old-account content and
keeps pending progress isolated in its existing account-bound outbox. Telegram
Mini Apps retain the identity provided by Telegram; this flow is for browsers.

## Security and deployment

- Codes are random 256-bit secrets, valid for five minutes and one redemption.
- Only the authenticated sender in a private bot chat can request a link.
- Credentials bypass conversation/LLM logging. Links are in URL fragments, not
  query strings. The login page strips the fragment and retains it only in memory.
- Only a SHA-256 digest is stored, in the existing `auth_sessions` table under
  `auth_method=browser_login_code`. These records cannot authenticate API calls.
- Preview does not consume the code. Confirmation binds to the displayed user
  ID. Atomic DELETE RETURNING + INSERT in one transaction prevents replays and
  rolls back consumption if session creation fails.
- A new code supersedes older codes for that account. Existing sessions are not
  revoked. The real browser session uses the existing 90-day policy.
- No new schema, service or BotFather configuration. Ship bot **and** web app;
  web-only deployment is insufficient. No production data repair is involved.
- Treat sign-in links like passwords. Never forward them or use unsolicited
  links. Reloading the confirmation page discards the in-memory code; reopen the
  bot link or paste it again. Incognito and cookie deletion are not required.

Tests: `pytest tests/webapp/test_browser_login.py`; frontend `npm run build` and
`node --test scripts/test_browser_login.cjs` from `webapp_frontend/`.
