# PDF Reader UX Improvement Plan

**Status:** Draft
**Last updated:** 2026-05-06
**Owner:** TBD
**Scope:** `webapp_frontend/src/pages/PdfReaderPage.tsx` and the backend highlight endpoints in `tm_bot/webapp/routers/content.py`.

This plan captures investigation findings and a prioritized action list for improving the PDF reading experience in the Xaana web app. Priorities are UX-first: visible quality and interaction friction come before architectural cleanup.

---

## Current State (Investigation Findings, 2026-05-06)

### Tech stack
- **Library:** `pdfjs-dist` v5.7.284, legacy build. Imported in `webapp_frontend/src/pages/PdfReaderPage.tsx:3-11`.
- **One mega-component:** `PdfReaderPage.tsx` is ~1093 lines and owns canvas rendering, text-layer wiring, touch gestures, highlight CRUD, popover, and dwell-time tracking.
- **Persistence:** Highlights are stored server-side. Endpoints in `tm_bot/webapp/routers/content.py:311-405`; repository in `tm_bot/repositories/content_repo.py:540-682`. Schema migration `tm_bot/db/alembic/versions/020_add_pdf_highlights.py`. Rects are stored as normalized 0–1 coords with `page_index`.
- **Tests:** Only backend CRUD coverage in `tests/webapp/test_content_pdf_router.py`. No frontend interaction tests for selection, rotation, RTL, or gestures.

### Notable PDF.js configuration (`PdfReaderPage.tsx:460-469`)
Currently disabled for webview compatibility:
- `disableAutoFetch: true`
- `disableRange: true`
- `disableStream: true`
- `useWasm: false`
- `isOffscreenCanvasSupported: false`
- `useSystemFonts: true` (enabled — keep)

These were turned off for the Telegram in-app webview. They hurt large-PDF performance. Worth re-checking which are still required.

### Pain points and root causes

| Symptom | Root cause | File / line |
|---|---|---|
| Render looks soft when zoomed in | `devicePixelRatio` clamped to **2** even on 3x devices (modern iPhones) | `PdfReaderPage.tsx:524` |
| Pinch/pan feels janky | Custom touch handler rebuilds the text layer on every scale change instead of using a CSS transform during the gesture | `PdfReaderPage.tsx:212-235`, `794-841`, `542-557` |
| Highlight popover hides selected text | Hard-coded `top: firstRect.y * pageBox.height - 48`. No flip-below near top edge, no viewport clamp, fixed 240px width | `PdfReaderPage.tsx:289-290`, `981-1016` |
| Persian/Arabic (RTL) selection awkward | Text-layer CSS has no RTL handling (`text-align: initial`, no `direction`). Rect-normalization in `captureSelection` assumes LTR ordering, so multi-line RTL selections produce wrong rects | `PdfReaderPage.tsx:244-294`, `webapp_frontend/src/styles/index.css:241-266` |
| Rotation breaks selection | Rotation is **not implemented** at all — no state, no toolbar, no CSS rotate. Any "rotated" view came from device orientation, and the text layer was never made rotation-aware | n/a |
| Large PDFs slow to load | `disableRange` + `disableStream` mean the entire file is fetched before render starts | `PdfReaderPage.tsx:460-469` |

---

## Prioritized Action Plan

Priority is by **user-visible impact first**, then by what unblocks later work.

### P1 — Render quality (high impact, low risk)
**Goal:** Sharp text on all devices.

- [x] **P1.1 done (2026-05-06):** DPR cap raised from 2 to 3 with a 16M-pixel canvas budget so very large/zoomed pages degrade gracefully. `PdfReaderPage.tsx:524-532`.
- [x] **P1.2 done (2026-05-06):** Bigger fix than the original line implied. Wired up PDF.js cmaps + standard fonts via `vite-plugin-static-copy` so Persian/Arabic/CJK CID-font PDFs get correct glyph→Unicode mapping (selection/copy now produces real text). `vite.config.ts`, `PdfReaderPage.tsx:471-475`. `useSystemFonts: true` left in place — useful when PDFs reference but don't embed standard fonts.
- [x] **P1.3 deferred (2026-05-06):** Investigated. PDFs are pre-fetched as bytes via auth-gated `apiClient.fetchPdfBlob` (`PdfReaderPage.tsx:306`) then passed to PDF.js as `data:` — which bypasses PDF.js's own fetching entirely, making the `disable*` flags no-ops in this flow. Re-enabling streaming would require rewiring auth (forwarding tokens to a signed URL fetched directly by PDF.js) and is not worth it for chapter-sized PDFs. Reopen if multi-hundred-MB PDFs become a use case.

### P2 — Highlight popover positioning (small, very high UX win)
**Goal:** Popover never hides what the user just selected.

- [ ] Flip-below logic when selection is near the top of the viewport.
- [ ] Clamp horizontally to viewport (not page) bounds so it doesn't go off-screen on rotated phones.
- [ ] Optional small arrow/caret pointing at the selection rect.
- [ ] Reconsider fixed 240px width — let it size to content with a max-width.

### P3 — RTL (Persian / Arabic) text selection
**Goal:** Selecting words and lines in Persian/Arabic feels native.

- [ ] Detect RTL per page using `textContent.items[].dir` from PDF.js (or per-span `direction` attribute on the text-layer divs).
- [ ] Fix rect normalization in `captureSelection` so right-anchored multi-line selections produce the correct rect order and bounding box.
- [ ] CSS audit: review `direction`, `text-align`, and `transform-origin` on text-layer spans for RTL pages.
- [ ] Add a smoke test with a Persian PDF fixture (multi-line selection across two RTL lines).

**Open question:** Should the toolbar/UI flip RTL when the document is RTL, or only the text layer? See architectural questions below.

### P4 — Pinch / zoom smoothness
**Goal:** Pinch feels continuous, not stepped.

- [ ] During an active pinch gesture, apply CSS `transform: scale(...)` to the page frame instead of re-rasterizing on every move event.
- [ ] On gesture end, set the new scale and re-render the canvas + text layer at the final scale.
- [ ] Preserve viewport anchor across the rasterize step (the existing `pendingViewportAnchorRef` logic already does most of this — extend it).
- [ ] Add momentum/inertia for pan, or rely on native overflow scroll.

### P5 — Component split (refactor that unblocks future work)
**Goal:** Make `PdfReaderPage.tsx` testable and changes safer.

Extract from the 1093-line file:
- [ ] `usePdfDocument` — load + page cache.
- [ ] `useTextSelection` — selection capture and rect normalization (RTL-aware after P3).
- [ ] `usePinchZoom` — gesture handling (after P4).
- [ ] `<HighlightPopover>` — popover component (after P2).
- [ ] `<HighlightLayer>` — saved-highlight rendering.

This is the prerequisite for clean implementation of P6.

### P6 — Rotation (do it properly, not via CSS)
**Goal:** Rotation is a first-class state and selection still works.

- [ ] Add a `rotation` state (`0 | 90 | 180 | 270`) and pass it to `page.getViewport({ scale, rotation })`. PDF.js then rebuilds the text layer in rotated coordinates and selection works natively.
- [ ] Toolbar control with rotate-left / rotate-right buttons.
- [ ] Persist per-document rotation preference (extend `content_highlight` table or a separate `content_view_state` table — TBD).
- [ ] Verify highlights stored in non-rotated coords still render correctly when the page is viewed rotated.

### P7 — Test coverage for PDF interactions
- [ ] Frontend tests (Vitest + Testing Library) for selection capture, popover positioning, and rotation.
- [ ] RTL fixture: at least one Persian and one Arabic PDF in `tests/fixtures/`.
- [ ] Visual regression on a few sample pages (optional — Playwright snapshots).

---

## Architectural Decisions Pending

These should be settled before P5 and P6 begin, since they shape the refactor:

1. **Stay on raw `pdfjs-dist` or move to `react-pdf`?**
   - Raw gives full control over the text layer and highlight overlay (we already have it).
   - `react-pdf` would shrink the component but we'd need to re-glue the dwell tracker, heatmap, and highlight overlay.
   - **Tentative recommendation:** stay on raw.

2. **RTL: per-document or app-wide default?**
   - If most content is Persian/Arabic, the reader could default to RTL toolbar layout, swapped ←/→ keys, and right-edge scroll affordances.
   - Alternative: detect per document from `textContent.items[].dir` and adapt only for that document.
   - **Decision needed.**

3. **Where does rotation state live?**
   - Per-user / per-document on the server (extends DB).
   - Per-document in `localStorage` (simpler, no DB change).
   - **Tentative recommendation:** `localStorage` for v1, server later if cross-device sync becomes a request.

---

## Out of Scope (for now)

- PDF annotations beyond highlights (freeform drawing, sticky notes, shapes).
- OCR for scanned PDFs.
- PDF editing/saving back.
- Multi-column layout reflow.

---

## Reference Files

- `webapp_frontend/src/pages/PdfReaderPage.tsx` — main reader component.
- `webapp_frontend/src/styles/index.css:79-420` — PDF reader styles (text layer, popover, page frame).
- `tm_bot/webapp/routers/content.py:311-405` — highlight endpoints.
- `tm_bot/repositories/content_repo.py:540-682` — highlight persistence.
- `tm_bot/db/alembic/versions/020_add_pdf_highlights.py` — schema.
- `tests/webapp/test_content_pdf_router.py` — backend CRUD tests (the only PDF-related tests today).

Recent relevant commit: `66a8b5f` — *Unified content library with PDF read tracking and highlights*.
