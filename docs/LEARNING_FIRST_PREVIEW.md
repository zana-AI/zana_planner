# Learning-first UI — local review slice

## Included

- Today, Library, Explore navigation. No people directory, active-user panels or follow counts in the main UI; social APIs and data remain intact.
- Empty Today leads into starter videos with a secondary Browse more action (Explore / Library remain the fallback when no picks are ready). Video saving is explicitly labelled Save to Library, not calendar planning. Starter videos require both editorial eligibility and cached captions matching the catalog's learning language.
- A separate routine card offers Learn English and Learn French topic presets plus Choose another topic. Each opens the same editable learning goal. Weekly-time presets do not schedule appointments or create anything until confirmed.
- Library keeps its side-thumbnail cards. Review is in the header; square + and filter buttons sit beside search. Empty Library points to Explore.
- Explore shows content immediately, with a single horizontally scrollable subject/type filter row and no duplicate introduction beneath the header. Icons, labels and subtle accents distinguish videos, courses, practice decks, habits, reading and clubs. Existing subject URLs still work.
- Explore defaults to Watch. All is an explicit filter, so routines and clubs don't interrupt the initial video selection. Course/practice cards open details, never enroll from discovery. Existing participation and club data remain unchanged.
- Compact side-thumbnail videos group creator metadata and controls; the bookmark is a labelled, 44px icon button. Nonvideo cards use small tinted icons and a single detail/setup action. Descriptions stay secondary on phones. Official Friends clips complement the four starter picks.
- Club management/creation remains reachable from Explore's Clubs filter. Only public active clubs and the viewer's active memberships are discoverable. No membership lists are sent in discovery cards.
- Caption readiness comes from existing tables. The four approved starter videos include verified catalog durations and creator attribution; newer DB duration metadata takes precedence. Full video duration is never inferred from the last subtitle cue. No schema changes or social-data migrations.
- All four approved starter videos appear in Explore; Today shows two ready picks, prioritizing different spoken languages before repeats (initially Jamy + TED-Ed procrastination). Earlier videos remain in Explore but are no longer starter suggestions.

## Safe localhost review

The regular local-preview launcher connects to production data. **Do not use it for this review.** This separate sandbox never loads .env or the application backend and has no DB or upstream API connector.

Terminal 1, from the repository root (Python with PyYAML):

```powershell
python scripts/design_preview.py
```

Terminal 2, from webapp_frontend:

```powershell
npm.cmd run dev -- --config vite.design.config.ts
```

Open <http://127.0.0.1:5174/dashboard?preview=empty&lang=en>.
The purple review strip switches between a new user, a returning learner, English/Persian and a 390px phone frame. Vite hot reloads changes.

All accounts, progress, club cards and subtitle readiness in this sandbox are fixtures. Starter video durations come from the verified catalog; other sample durations remain simulated. Adding sample videos and confirming a routine changes memory only; restarting the fixture server resets it. Actual playback, Telegram, real club creation and other mutations are intentionally disconnected and return an explicit preview error. Stop both processes with Ctrl+C. Preview controls are injected only by the opt-in Vite config, never the normal build.

## Next slices, not included

1. Grow an editorially reviewed educational catalog, particularly English; don't auto-publish private Library imports. See [the researched starter shortlist](STARTER_CONTENT_SHORTLIST.md). Check original-language subtitles and playback before promotion.
2. Continue-watching and daily learning history based on reliable event timestamps, watched ranges and full video duration. Don't invent activity from cumulative progress.
3. Explicit public recommendations, with source creator separate from recommending user, visibility controls and reporting/moderation. No automatic public sharing.

The user approved shipping this slice on 2026-09-24. The fixture server and design-only Vite config remain opt-in local tools and are not the production backend.
