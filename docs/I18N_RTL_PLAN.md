# Persian (fa) Localization & RTL Plan

Status: **SHIPPED 2026-08-27** — Phases 1–4 complete, Persian live for all users.
Written 2026-08-26.

Persian is selected from **Settings → Language**, and is the default for anyone whose
Telegram account language is `fa`. `?lang=<code>` on any route still forces a language
for previewing (sticky for the session).

**Kill switch:** remove `'fa'` from `RELEASED_UI_LANGUAGES` in
`webapp_frontend/src/i18n/index.ts` and redeploy. That reverts the webapp to English
without touching the catalogs; the Telegram bot keeps translating either way.

**Not shipped:** Phase 5 (bot `.po` catalogs) and D3 (Saturday week start). See §8.

Goal: ship a fully Persian, right-to-left Xaana Mini App, without regressing the
English experience and without a rewrite.

---

## 1. Audit — where we actually stand

The good news: this codebase is *much* closer to RTL-ready than a typical React app,
because almost all layout is flexbox/grid with logical spacing already.

### Already in place

| Thing | Where | Notes |
|---|---|---|
| `language` column on user settings | migration `001_initial_schema.py:38` | `en` / `fa` / `fr` |
| Language picker UI | `webapp_frontend/src/pages/SettingsPage.tsx:8` | already offers Persian; only affects the *bot*, not the webapp |
| `PATCH` settings endpoint | `apiClient.updateUserSettings({ language })` | wired end-to-end |
| Bot language enum | `tm_bot/handlers/messages_store.py:10` | `EN`, `FA`, `FR` |
| `babel==2.17.0` | `requirements.txt:10` | already a dependency — gives us `.po` catalogs + `fa` number/date formatting for free |
| Telegram locale hint | `initDataUnsafe.user.language_code` | available via `useTelegramWebApp`, currently unused |

### The RTL surface is small

Measured across `webapp_frontend/src`:

- **13** inline directional style props (`marginLeft` ×10, `paddingLeft` ×2, `marginRight` ×1) across 7 files — 4 of them admin-only.
- **~120** `left:` / `right:` / `text-align: left|right` declarations across 24 files. A large share are absolute-positioning for sheets/popovers, and the `pdfReader/*` ones (`types.ts`, `useTextSelection.ts`, `usePinchZoom.ts`, `useHighlightPopover.ts`) are **DOMRect coordinate math, not CSS** — they must NOT be blindly converted.
- **21** direction-sensitive icons (`ChevronLeft/Right`, `ArrowLeft/Right`, `Undo`).
- **14** `translateX` usages (sheet/carousel animation).
- **~0** float-based or absolutely-hardcoded layouts.

Realistically this is **1–2 days of layout work**, not weeks.

### The real cost is strings and dates

- **24,532** LOC of TS/TSX total; **16,111** in non-admin TSX, **4,088** in admin TSX.
- A conservative regex sweep of non-admin components finds **202** JSX text nodes and
  **104** translatable attributes (`placeholder` / `title` / `aria-label` / `label`).
  Expect the true count after extraction to land around **450–650 strings** once
  conditionals, template literals and toast messages are included.
- **20** `toLocaleDateString('en-US', …)` / `toLocaleTimeString('en-US', …)` call sites,
  plus hardcoded weekday arrays in `PromiseCard.tsx:609` and `admin/CreatePromiseTab.tsx:37`.
- **359** `detail=` strings across `tm_bot/webapp/` (353 in `routers/*`, the rest in
  `api.py` and `dependencies.py`). These *are* user-visible:
  `api/client.ts:251` surfaces `errorData.detail` straight into toasts. Most are
  technical, but the ~40 that represent real user errors (validation, quota, auth)
  need codes rather than prose.

### The blockers nobody has looked at yet

1. **No Persian glyphs are loaded.** `main.tsx:3-6` imports Manrope (Latin only) and
   `index.html:20` pulls Google's `Noto Sans` — which is *not* `Noto Sans Arabic`.
   Persian text today renders in whatever the OS falls back to. On Telegram Desktop
   that's usually fine; on Android it is inconsistent and ugly.
2. **`<html lang="en">` is hardcoded** (`index.html:2`). No `dir` attribute anywhere.
3. **Week starts Monday, everywhere.** `tm_bot/utils/time_utils.py:29`
   (`reference - timedelta(days=reference.weekday())`) and
   `DashboardPage.tsx:79` (`getCurrentWeekMonday`). The Iranian week runs
   **Saturday → Friday**. This is the single decision with data-model consequences —
   see §2.
4. **Mixed-direction content is the norm, not the exception.** Our flagship Persian-audience
   content is Atena's *French* vocab challenge. Every card is a French/Latin string
   inside a Persian RTL container. Without `dir="auto"`, trailing punctuation and
   parentheses will jump to the wrong end of the line.
5. **Bot translation is LLM-at-runtime.** `messages_store.py:250` calls
   `translate_text()` (Groq) on every non-English message. That means per-message
   latency, cost, and non-deterministic wording — the same button reads differently
   on two different days. Static UI strings should not go through an LLM.

---

## 2. Decisions to make first

These change the shape of the work. Recommendations given; all three are yours to overrule.

### D1 — Persian digits (۱۲۳) or Latin digits (123)?

**Recommendation: Persian digits for display, Latin everywhere machine-readable.**

This is the standard split in Iranian products (Digikala, Snapp, bank portals):
Persian digits in prose, counters, dates, and durations; Latin digits in phone
numbers, tracking codes, URLs, and anything copy-pasteable. `Intl.NumberFormat('fa-IR')`
does this for free — no library.

Caveat for us: numeric **inputs** must accept both, and normalise Persian/Arabic-Indic
digits back to Latin before hitting the API. One `toLatinDigits()` helper on every
numeric input (`LogTimeSheet`, `DurationWheelPicker`, promise hours).

### D2 — Jalali (Shamsi) calendar?

**Recommendation: yes, for display, from day one.**

Persian speakers do not read Gregorian dates. A weekly-promise app that shows
"Mar 3 – Mar 9" to an Iranian user is unusable. `Intl.DateTimeFormat('fa-IR')`
already defaults to the Persian calendar in every browser we support — **zero
bundle cost** for all 20 display call sites.

A library is only needed for the *interactive* calendar grid
(`InlineCalendar.tsx`), which needs Jalali month lengths and leap years:
`jalaali-js@2.0.1` (~2 KB) is the stable, boring choice.
(`date-fns-jalali` is currently only on a `4.4.0-0` prerelease — skip it.)

### D3 — Does the Persian week start Saturday?

**Recommendation: yes, but make it a per-locale setting, not a global flip.**

This is the expensive one. `get_week_range()` is a single choke point, which is
lucky — but weekly progress, weekly reviews (`promise_weekly_reviews.week_start`),
the weekly report, and the nightly/morning schedulers all key off it. Changing the
boundary for existing users **re-buckets their history**.

Proposed approach:
- Add `week_start_day` to user settings (0=Mon … 5=Sat), defaulting to Sat for `fa`
  and Mon otherwise.
- Thread it through `get_week_range(reference, week_start_day)` and the frontend
  equivalent. It is one function on each side.
- **Do not backfill.** New buckets from the switch date forward; old rows keep their
  Monday boundaries. Attempting to re-slice historical `week_start` rows is not worth it.

If you want to defer this: ship Persian UI with a Monday week first (D3 = "later"),
and treat Saturday-week as a fast-follow. Everything else in this plan is independent of D3.

### D4 — Where do translations come from?

**Recommendation: static catalogs, reviewed by a native speaker. Retire the runtime LLM path for UI strings.**

- Webapp: JSON catalogs (`locales/en.json`, `locales/fa.json`).
- Bot: Babel `.po` (we already have Babel).
- Seed both with an LLM pass, then have Atena — a working language teacher and our
  first partner — review. Machine-only Persian in a *language-learning* product is a
  credibility problem, not just a polish problem.
- Keep `translate_text()` alive **only** for genuinely dynamic content (LLM replies,
  user-authored promise text, summaries).

---

## 3. Architecture

### Webapp

Add `i18next` + `react-i18next@17`. Not hand-rolled: interpolation, fallback chains,
lazy namespace loading and CLDR plural rules are all things we'd otherwise rebuild badly.
(Persian has `one`/`other` cardinal forms — different from English in practice for
fractional quantities.)

```
webapp_frontend/src/i18n/
  index.ts          # i18next init, lang detection, dir side-effect
  locales/en.json   # source of truth
  locales/fa.json
  format.ts         # formatNumber / formatDate / formatDuration / toLatinDigits
```

**Direction is a document-level effect, not a prop.** One `useEffect` in `i18n/index.ts`:

```ts
document.documentElement.lang = lng;
document.documentElement.dir = RTL_LANGS.has(lng) ? 'rtl' : 'ltr';
```

Everything else follows from CSS logical properties. Do **not** add a `dir` prop to
components, and do not build an `isRtl` conditional style pattern — that is the
mistake that turns a 2-day job into a 3-week job.

Language resolution order:
1. explicit user setting from `/users/me` (authoritative, already exists)
2. `tg.initDataUnsafe.user.language_code`
3. `navigator.language`
4. `en`

### Backend / bot

- `tm_bot/i18n/` with Babel `.po` catalogs per language; `get_message()` in
  `messages_store.py` reads the catalog first and falls back to
  `translate_text()` only on a missing key (with a warning log, so gaps surface).
- Replace the ~40 user-facing `detail="…"` strings in the routers with stable
  `error_code` values in the response body; the webapp maps codes → localised copy.
  Leave the technical ones (`"promise not found"` on an admin route) as English prose.

### Fonts

- `@fontsource-variable/vazirmatn@5.3.0` — self-hosted, variable, covers Persian +
  Arabic, and is the same face Telegram Desktop itself uses for Persian. Self-hosting
  also removes the Google Fonts CDN dependency in `index.html`.
- Set it as a fallback *after* Manrope in `--font-sans`, so Latin text keeps our
  brand face and Persian glyphs resolve to Vazirmatn automatically. No conditional
  font stacks needed.
- Persian needs more vertical room: bump `line-height` ~15% under `[dir="rtl"]`
  (`1.5` → `1.7`) and set `letter-spacing: normal` — Persian is cursive and any
  positive tracking breaks the joins.
- Drop the `Noto Sans` Google link; it isn't doing what it looks like it's doing.

---

## 4. Phased plan

### Phase 0 — Decisions (½ day)
Resolve D1–D4. Nothing below is safe to start until D3 is at least deferred-or-not.

### Phase 1 — Foundation ✅ DONE (2026-08-27)
- Installed `i18next@26`, `react-i18next@17`, `@fontsource-variable/vazirmatn@5`.
  (Note: `react-i18next@17` requires `i18next >= 26.2`; `i18next@25` will not resolve.)
- `src/i18n/` — `index.ts` (init, resolution, `dir`/`lang` side-effect),
  `format.ts` (Intl number/date + `toLatinDigits`), `useServerLanguageSync.ts`,
  `locales/{en,fa}.json`.
- Font stack: Vazirmatn added to `--font-sans` **after** Manrope, so per-character
  fallback covers Persian while Latin stays on brand. The family name is
  `"Vazirmatn Variable"` — the bare name silently falls back.
  Dropped the Google `Noto Sans` link from `index.html`: it has no Arabic coverage,
  so it never did what its name suggested.
- RTL typography block in `design-system.css` — looser leading, zeroed tracking,
  `text-transform: none`, plus the `.icon-directional` and `.numeric-ltr` helpers.
- `?lang=fa` preview override, persisted in sessionStorage so it survives
  react-router navigation.
- **Gate:** `RELEASED_UI_LANGUAGES = ['en']` in `src/i18n/index.ts`. The Settings
  picker keeps setting the *bot* language for `fa`/`fr` exactly as before; it only
  switches the webapp UI for released languages. Adding `'fa'` there is the ship switch.

**Verified** (headless Chromium against a production build): default load stays
`ltr`/`en`; `?lang=fa` yields `dir="rtl"`/`lang="fa"`; the override survives
navigation; RTL token overrides apply (`--lh-body` 1.5 → 1.72, `--tracking-tight` → 0);
Vazirmatn resolves for Persian text; no page errors.

> Testing note: `npm run preview` **cannot** serve this app. Vite's `preview.proxy`
> defaults to `server.proxy`, and `vite.config.ts` proxies `/assets` to the backend on
> :8080 — so preview 500s on its own bundle and the app never boots. Serve `dist` with
> any static server that has SPA fallback instead.

### Phase 2a — App shell ✅ DONE (2026-08-27)
`Navigation`, `BottomNav`, `SettingsPage` fully translated (page titles/subtitles,
nav labels, profile menu, aria-labels, toasts). `getShellPageMeta()` now returns
catalog keys rather than English strings.

### Phase 2 — String extraction ✅ DONE (2026-08-27)
Translated: shell (`Navigation`, `BottomNav`, `PageHeader`), `DashboardPage`,
`PromiseCardV2`, `PromiseCard`, `PromiseDetailSheet`, `CheckinSheet`, `LogTimeSheet`,
`PlaySheet`, `ScheduleSheet`, `SettingsPage`, `ChallengesPage`, `ChallengeDetailPage`,
`ChallengePlayPage`, `FlashcardsPage`, `TemplatesPage`, `UsersPage`, `ClubBadge`,
`UserCard`, `UserDetailPage`, `WeeklyReport`, `utils/activitySummary`.

Verified by a headless sweep of `/dashboard`, `/challenges`, `/flashcards`, `/settings`,
`/community`, `/templates` at `?lang=fa`: every route renders `dir="rtl"` with Persian
copy and **zero** Latin digits; the only Latin text left is user/mock content and the
language endonyms, which is correct.

Original slice order, for reference:
1. ~~Shell — `Navigation`, `BottomNav`, `PageHeader`~~ ✅
2. `DashboardPage` + `PromiseCardV2` + `PromiseDetailSheet` (the daily loop)
3. Sheets — `CheckinSheet`, `LogTimeSheet`, `ScheduleSheet`, `FocusSheet`, `PlaySheet`
4. `ChallengesPage`, `ChallengePlayPage`, `FlashcardsPage` (the Persian-audience surface)
5. `SettingsPage`, `ClubProfilePage`, `WeeklyReport`
6. `utils/activitySummary.ts` + `activityFormat.ts` — these *generate* English prose
   (`"3 activities this week"`, `"1 day ago"`) and need to become `t()` calls with counts,
   not string concatenation.
7. **Admin panel: skip.** 4,088 LOC, internal-only, English is fine. Say so explicitly
   in the catalog README so nobody "finishes the job" later.

### Phase 3 — RTL layout pass ✅ DONE (2026-08-27)

- 20 box-model longhands → `margin-inline-*` / `padding-inline-*` / `border-inline-*`.
- 17 `text-align: left|right` → `start|end`.
- 15 single-sided absolute offsets → `inset-inline-start|end`.
- **Deliberately left physical:** symmetric `left:0; right:0` pairs (direction-neutral),
  `left: 50%` centering idioms, and every `env(safe-area-inset-left|right)` — the notch
  is on a *physical* side regardless of text direction.
- **Never converted:** `pdfReader/{types,useTextSelection,usePinchZoom,useHighlightPopover}`
  — those `left`/`right` values are DOMRect geometry, not CSS.
- Directional icons given `.icon-directional` (`scaleX(-1)` under RTL): DashboardPage
  week chevrons, PageHeader + Navigation back arrows, PdfReader arrows and page chevrons.
- `HomePage` and `AdminPanel` pinned `dir="ltr"` — their copy stays English by design
  (§6), and mirroring an untranslated page reads as a bug.
- Spans previously pinned `dir="ltr"` that now carry translated prose (`PlaySheet`,
  `ClubBadge`, day labels) switched to `dir="auto"`. Genuinely numeric spans
  (`#id`, percentages in cards) stay LTR.

Verified geometrically: the `+` FAB sits 18px from the **left** under `fa` and 18px from
the **right** under `en`; chevrons compute to `matrix(-1, 0, 0, 1, 0, 0)` under RTL and
`none` under LTR.

- Mechanical: `margin-left` → `margin-inline-start`, `padding-right` → `padding-inline-end`,
  `text-align: left` → `text-align: start`, `left:` → `inset-inline-start:` for
  *positioned* elements.
- **Do not touch** `pdfReader/types.ts`, `useTextSelection.ts`, `usePinchZoom.ts`,
  `useHighlightPopover.ts` — those `left`/`right` values are DOMRect geometry.
- Mirror the 21 directional icons via a `<DirectionalIcon>` wrapper or
  `[dir="rtl"] .icon-directional { transform: scaleX(-1) }`.
- Audit the 14 `translateX` uses — sheet slide-ins are vertical (fine), but any
  horizontal carousel/swipe needs its sign flipped under RTL.
- Progress/heatmap fills: `HeatmapBar`, `FocusBar`, promise progress bars must fill
  from the right under RTL. Exception: the PDF read-coverage bar should follow the
  *document's* direction, not the UI's.
- `InlineCalendar`: Jalali grid + Saturday-first columns (depends on D2/D3).
- Add `dir="auto"` on every element rendering user- or content-supplied text —
  promise titles, club names, and **every flashcard/challenge field**. Wrap inline
  foreign fragments in `<bdi>`. This is the single highest-value RTL change for our
  actual content.
- Respect the existing safe-area work — see the iPhone-notch memo; the landscape
  inset logic is direction-sensitive.

### Phase 4 — Numbers & dates ✅ DONE (2026-08-27)
- `i18n/format.ts`: `formatNumber`, `formatDate`, `formatDateRange`, `intlLocale`,
  `weekdayNarrowLabels`, `weekdayLongLabels`, `toLatinDigits`, `parseLocalizedNumber`.
- All 20 `toLocaleDateString('en-US')` / `toLocaleTimeString('en-US')` call sites replaced.
  Persian now shows **Jalali dates with Persian digits** — e.g. `۲ تا ۸ شهریور ۱۴۰۵` —
  entirely via `Intl`, zero added bundle weight, exactly as D2 predicted.
- Hardcoded weekday arrays replaced with locale lookups, resolved **per render** so a
  language switch applies immediately (a module-level constant would freeze at import).
  Ordering stays Monday-first to match the backend's week buckets — that is D3, not this.
- Interpolated numbers localized via an i18next `num` formatter
  (`{{count, num}}`), so plural selection still uses `count` while display uses locale
  digits. Note: i18next v26 removed `interpolation.format`; use
  `i18next.services.formatter.add(...)`.

> `toLatinDigits` / `parseLocalizedNumber` exist and are exported, but the numeric
> **inputs** are not yet routed through them. A Persian keyboard producing `۳٫۵` in the
> log-time field will still fail to parse. First follow-up — see §8.

### Phase 5 — Bot & backend parity (2–3 days)
- Babel `.po` catalogs; `get_message()` catalog-first.
- Persian date formatting in bot messages (`message_handlers.py:508` builds
  `"%d %b - %d %b"` ranges by hand).
- Error codes for the ~40 user-facing `detail=` strings.
- D3, if accepted: `week_start_day` setting + threading through `get_week_range()`.

### Phase 6 — QA & rollout (1–2 days)
- Playwright screenshot pass at `?lang=fa` across the main routes (we already have
  `scripts/render_home_screenshots.mjs` to build on).
- Native review — Atena for copy, plus one non-technical Persian speaker on a real phone.
- Ship: enable `fa` in the webapp picker, default it on for users whose Telegram
  `language_code` is `fa`, keep an easy switch back to English.

**Total: roughly 2–3 focused weeks**, of which Phase 2 is half.

---

## 5. Persian/RTL specifics worth internalising

Things that reliably get missed:

- **`direction: rtl` is not localisation.** It mirrors the box model and nothing else.
  Icons, animations, charts, and shadow offsets all need separate attention.
- **Not everything mirrors.** Numbers, phone numbers, code, URLs, media playback
  controls, and clock faces stay LTR. Progress-through-time bars *do* mirror.
- **ZWNJ (U+200C) is a real character in Persian.** `می‌روم` is one word with a
  zero-width non-joiner. Translators will use it; do not strip it in sanitisation,
  and do not let a "trim whitespace" helper eat it.
- **Persian has no letter case.** Any `text-transform: uppercase` on a shared class
  is a no-op in Persian but will silently upper-case interleaved Latin words — check
  button styles.
- **Persian text is taller and needs more leading**, and it renders visually smaller
  at the same `font-size`. Consider a small size bump under `[dir="rtl"]`.
- **Truncation and ellipsis** behave differently; verify `text-overflow: ellipsis`
  on promise titles renders the ellipsis on the correct side.
- **Mixed-direction punctuation** is the classic bug: `«فرانسه (French)»` will
  misplace its parentheses without `dir="auto"`/`<bdi>`. Given our content, test this early.
- **Comma is `،` (U+060C) and the decimal separator differs.** `Intl` handles it; hand-built
  `join(', ')` calls do not.

---

## 6. Explicitly out of scope

- Admin panel (`components/admin/*`, 4,088 LOC) — stays English.
- Arabic or Hebrew. The RTL work makes them cheap later, but no catalogs now.
- Localising user-generated content (promise text, club descriptions).
- Backfilling historical `week_start` rows if D3 is accepted.
- LLM conversational replies — those already localise via the existing runtime path.

---

## 8. Not shipped / follow-ups

1. **Numeric inputs don't normalize Persian digits yet.** `toLatinDigits()` is written and
   exported but unwired. `LogTimeSheet`, `DurationWheelPicker` and the promise-hours field
   need it before a Persian-keyboard user can log time. Highest-priority follow-up.
2. **Phase 5 (bot) not started.** The Telegram bot still LLM-translates at runtime via
   `translate_text()`. Works, but costs latency and wording drift.
3. **D3 (Saturday week start) not shipped.** Deliberate: it re-buckets existing weekly
   history for *all* users, English included, and was never actually chosen.
4. **`InlineCalendar` shows a Gregorian grid with Persian labels.** Display dates are
   Jalali everywhere else, so the picker is now inconsistent. Needs `jalaali-js`.
5. **Persian copy is unreviewed.** Written by Claude, grammatical but not idiomatic in
   places. Atena should review before any Persian-language marketing push.
6. **`npm run lint` cannot run** — the script calls `eslint`, which is not in
   `devDependencies`. Pre-existing, unrelated to this work.

## 7. Open questions

1. D1–D4 above.
2. Does Atena have bandwidth to review ~500 Persian strings, and is that a paid task?
3. Do we want a Persian-language *marketing* surface (`/c/<club>` public landing pages
   are already public and indexable), or is Persian mini-app-only for now?
4. Should `fa` users get a Persian-localised bot **and** webapp simultaneously, or is
   webapp-first acceptable given the bot already half-translates via LLM?
