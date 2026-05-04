# PDF Reader V1 Plan

## Goal
Build Xaana's PDF reader into a real mobile reading surface: selectable text, synced highlights and notes, smooth page turns, clean fullscreen reading, and resumable progress across devices.

## Current Sprint
- [x] Add a repo-tracked implementation plan.
- [x] Add a PDF.js text layer above the canvas so long-press text selection works.
- [x] Convert selected text into normalized page rectangles.
- [x] Add a compact highlight/note popover from selected text.
- [x] Render saved highlights over the current page.
- [x] Add visible minimal edge arrows in fullscreen.
- [x] Add a smooth page-turn transition.
- [x] Verify frontend build and PDF backend tests.
- [x] Commit and push.

## Reader Layering
- [x] `canvasLayer`: PDF bitmap rendering via PDF.js.
- [x] `textLayer`: transparent PDF.js text layer, selectable and aligned with canvas.
- [x] `highlightLayer`: Xaana-synced highlight rectangles, normalized to the page.
- [x] `chromeLayer`: toolbar, fullscreen controls, page arrows, sync status.
- [ ] Keep pointer behavior explicit so selection, panning, edge arrows, and pinch zoom do not fight.

## Text Selection And Highlights
- [x] Render page text with `pdfjsLib.TextLayer`.
- [x] On `selectionchange` / touch selection end, detect selections inside the active text layer only.
- [x] Extract selected text from `window.getSelection()`.
- [x] Convert DOM `Range.getClientRects()` into page-relative `{ x, y, width, height }` rects.
- [x] Ignore empty selections and selections outside the current page.
- [x] Show a small action popover near the selection with `Highlight`, `Note`, and `Cancel`.
- [x] Save highlights through existing highlight API using `asset_id`, `page_index`, `rects`, `selected_text`, `note`, and `color`.
- [x] Clear native selection after save/cancel.
- [x] Re-fetch or optimistically append saved highlights after creation.
- [x] Render saved highlights by page and current asset.

## Fullscreen Reading
- [x] Hide Xaana app header and bottom navigation in fullscreen.
- [x] Use Telegram fullscreen API when available.
- [x] Use browser fullscreen when available.
- [x] Use CSS fixed fullscreen fallback everywhere else.
- [x] Auto-hide toolbar after a short delay.
- [x] Tap center to reveal toolbar.
- [x] Add visible but subtle left/right edge arrows for page turning.
- [x] Keep horizontal swipe page turning.
- [x] Preserve pinch zoom.
- [x] Keep exit fullscreen discoverable with an `X` button.

## Page Turning
- [x] Add direction-aware page transition state.
- [x] Animate next page in with short slide/fade.
- [ ] Disable animation while rendering is already busy.
- [x] Respect `prefers-reduced-motion`.
- [ ] Show a short page number toast after page turn.

## Later Reader Essentials
- [ ] Search text in PDF.
- [ ] Page thumbnails sheet.
- [ ] PDF outline/bookmarks sheet.
- [ ] User bookmarks synced to backend.
- [ ] Theme modes: day, sepia, night.
- [ ] Fit width / fit page / manual zoom presets.
- [ ] OCR or area highlights for scanned PDFs.
- [ ] Multi-page continuous reading mode.

## Backend And Data
- [x] Store PDF binaries outside PostgreSQL and keep them immutable.
- [x] Store highlights/notes/progress as metadata in PostgreSQL.
- [x] Resume using `user_content.last_position`.
- [x] Treat PDF progress events as resume checkpoints.
- [ ] Add user bookmark table only when implementing bookmarks.
- [ ] No new migration is needed for text highlights if existing `content_highlight.rects_json` remains sufficient.

## Test Checklist
- [x] Frontend build passes.
- [x] Existing PDF API/storage tests pass.
- [ ] Long-press/drag text selection works on Telegram mobile.
- [ ] Highlight appears immediately after save.
- [ ] Highlight remains aligned after zoom.
- [ ] Highlight remains aligned after close/reopen.
- [ ] Fullscreen hides Xaana nav in portrait and landscape.
- [ ] Fullscreen edge arrows turn pages.
- [ ] Swipe and pinch gestures do not conflict.
- [ ] Reduced-motion users do not get forced page animations.

## Assumptions
- First V1 implementation keeps one rendered page at a time.
- Scanned/image-only PDFs will show no selectable text until OCR support is added.
- Highlights remain Xaana metadata and are not embedded back into PDF files.
- Edge arrows are visible in fullscreen because discoverability matters more than pure invisibility.
