# PDF Reader UX Improvement Plan

**Status:** Draft
**Last updated:** 2026-05-06
**Owner:** TBD
**Scope:** PDF reader UX, backend PDF read tracking, PDF content analysis, and the learning features that support shared reading workflows.

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

### P2.5 — Safe-area handling for landscape on iPhone (added 2026-05-06)
**Goal:** The page-turn buttons must not sit under the camera/Dynamic Island in landscape orientation on iPhone 13+.

- [x] **Done (2026-05-06):** Added `viewport-fit=cover` to the viewport meta tag in `index.html:5`. The PDF reader's CSS already used `env(safe-area-inset-*)` for page-zone buttons, toolbar, and fullscreen toast — those env values were resolving to 0 because viewport-fit was missing. Now correctly resolves on iPhone 13+ in both landscape orientations.
- [ ] **Verify on device** (manual): test iPhone 13/14/15 in landscape, both rotations (notch left vs notch right). Smoke-check that nav buttons and toolbar inset away from the camera area.

### P3 — RTL (Persian / Arabic) text selection
**Goal:** Selecting words and lines in Persian/Arabic feels native.

- [x] **P3.1 done (2026-05-06):** Detect RTL per rendered page from PDF.js `span[dir]` output and set `dir` / `data-text-direction` on the text-layer container.
- [x] **P3.2 done (2026-05-06):** Selection capture now records DOM range rect direction, groups rects by visual line, orders RTL line fragments right-to-left, and saves merged normalized rects in the existing 0-1 schema.
- [x] **P3.3 done (2026-05-06):** CSS audit/fix: added the minimal PDF.js v5 text-layer transform/font-size rules that were missing locally, plus page/span `direction` and `unicode-bidi: isolate` handling. Kept PDF.js's `transform-origin: 0% 0%` because the official v5 viewer CSS uses the same origin for all text spans.
- [ ] Add a smoke test with a Persian PDF fixture (multi-line selection across two RTL lines).

**Open question:** Should the toolbar/UI flip RTL when the document is RTL, or only the text layer? See architectural questions below.

### P4 — Pinch / zoom smoothness & gesture cleanup
**Goal:** Pinch feels continuous, not stepped. Remove gestures that conflict with intentional interactions.

- [x] **Done (2026-05-06):** Removed single-finger swipe-to-change-pages in fullscreen (`PdfReaderPage.tsx` `handleTouchEnd`). Edge buttons (`pdf-reader-page-zone--prev`/`--next`) remain the only page-turn interaction; pinch-zoom preserved. Also dropped the unused `touchStartRef`.
- [x] **Done (2026-05-06):** During an active pinch gesture, apply CSS `transform: scale(...)` to the page frame instead of re-rasterizing on every move event.
- [x] **Done (2026-05-06):** On gesture end, commit the final scale and re-render the canvas + text layer once.
- [x] **Done (2026-05-06):** Preserve the pinch midpoint viewport anchor across the rasterize step using the existing `pendingViewportAnchorRef` flow.
- [x] **Done (2026-05-06):** Keep native overflow scrolling / `-webkit-overflow-scrolling: touch` for pan momentum instead of adding custom inertia.

### P5 — Component split (refactor that unblocks future work)
**Goal:** Make `PdfReaderPage.tsx` testable and changes safer.

Extract from the 1093-line file:
- [x] **Done (2026-05-06):** `usePdfDocument` — PDF.js document creation + initial page/scroll selection.
- [x] **Done (2026-05-06):** `useTextSelection` — selection capture and RTL-aware rect normalization.
- [x] **Done (2026-05-06):** `usePinchZoom` — gesture handling and CSS preview scaling.
- [x] **Done (2026-05-06):** `<HighlightPopover>` — popover component.
- [x] **Done (2026-05-06):** `<HighlightLayer>` — saved-highlight rendering.

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

### P8 — PDF page analysis and estimated reading time
**Goal:** Replace the fixed "15 seconds per page" assumption with low-cost, page-aware estimates.

- [ ] Add a server-side PDF analyzer that runs when a PDF is uploaded or when `/api/content/{content_id}/analyze` is requested.
- [ ] Use the existing `pypdf==5.9.0` dependency for v1 text extraction; do not add a paid parser for born-digital PDFs.
- [ ] For each page, calculate `page_index`, `word_count`, `char_count`, `estimated_read_seconds`, and `text_extractable`.
- [ ] Store aggregate fields: `page_count`, `total_word_count`, `estimated_read_seconds`, `analysis_method`, `needs_ocr`, and `analyzed_at`.
- [ ] Persist v1 output as a `content_artifact` with `artifact_type = "pdf_page_metrics"` and update `content.estimated_read_seconds` with the document total.
- [ ] Default reading speed: `PDF_READING_WPM=220`. Make this configurable later if real usage data shows it is consistently wrong for Persian/Arabic or dense technical material.

**Storage decision:** Use `content_artifact.payload_json` for page metrics in v1. Add a dedicated `content_page_metric` table only if later analytics needs efficient SQL filtering across pages/documents.

### P9 — Adaptive read-progress estimation
**Goal:** Reading completion should account for actual page density while staying compatible with the current heatmap system.

- [ ] Keep the existing heatmap buckets and progress APIs compatible.
- [ ] When page metrics exist, weight dwell/completion by each page's `estimated_read_seconds` instead of a global 15-second threshold.
- [ ] Use bounded per-page completion gates: never less than 8 seconds for text pages, and never more than 90 seconds for one page gate.
- [ ] Keep 15 seconds as the fallback for pages/documents without analysis metrics.
- [ ] Expose page metrics in the PDF open response or a nearby metadata endpoint so the reader can make client-side dwell decisions without extra round trips while reading.

### P10 — PDF support in the learning pipeline
**Goal:** Let uploaded PDFs use the existing summaries, Q&A, embeddings, concepts, and quiz pipeline.

- [ ] Add a `PdfIngestor` under `tm_bot/services/learning_pipeline/ingestors`.
- [ ] Route PDF content through `PdfIngestor` in the learning worker instead of falling through to blog ingestion.
- [ ] Convert extracted page text into `SegmentRecord`s with page-aware `section_path` values such as `pdf/page/12`.
- [ ] If PDF outlines/bookmarks are available, also emit chapter-aware section paths; otherwise support manually defined page ranges later.
- [ ] Reuse the existing `content_segment`, `content_artifact`, Qdrant, summary, Q&A, quiz, and concept extraction flows.
- [ ] Cache generated PDF summaries/Q&A seeds in `content_artifact`; do not regenerate costly LLM outputs unless the PDF asset changes or the user explicitly requests refresh.

### P11 — Shared reading and milestone workflows
**Goal:** Prepare the reader for small-community "we are reading this together" use cases without implementing the whole social layer yet.

- [ ] Research a lightweight reading-group model where a group shares one content item and has milestones defined by chapter, page range, or named section.
- [ ] Track enough metadata to answer: who is on track, who is behind, what pages/chapters are assigned next, and what discussion scope is active.
- [ ] Let milestone summaries and Q&A use scoped content ranges, for example "chapter 4", "pages 55-78", or "this week's milestone".
- [ ] Treat group schema, permissions, invitations, comments, and discussion UI as later product work after page metrics and scoped summaries are stable.

### P12 — External document and summary services research
**Goal:** Keep default costs low, but know which external services are worth integrating when local extraction is not enough.

- [ ] Default posture: local extraction first, existing Gemini/OpenAI learning pipeline second, external OCR/document parsing only as opt-in fallback when `needs_ocr = true` or layout quality is poor.
- [ ] Evaluate OCR/document parsing services for scanned PDFs, Persian/Arabic support, privacy/data retention, async job support, SDK complexity, and per-page cost.
- [ ] Candidate OCR/parsing services:
  - Google Document AI OCR: about `$1.50 / 1,000 pages`; layout/parser features cost more.
  - AWS Textract Detect Document Text: example pricing shows `$0.0015/page` for the first 1M pages in US West.
  - Azure Document Intelligence: keep as a candidate, verify region-specific pay-as-you-go pricing before choosing.
  - Unstructured: flat pay-as-you-go document processing at about `$0.03/page`, useful when richer structure is worth the extra cost.
  - Mistral OCR and LlamaParse: research candidates; verify current pricing, privacy posture, and RTL quality before integration.
- [ ] Candidate summary/Q&A providers:
  - Gemini Flash/Flash-Lite: preferred low-cost path because the repo already has Gemini integration.
  - OpenAI small/mini models: keep as fallback through the existing OpenAI gateway.
  - Claude Haiku: possible later fallback, but not needed for v1 because it adds a new provider.
- [ ] Do not send uploaded community PDFs to external processors by default. Require an admin/provider config and make the fallback visible in job metadata.

---

## Architectural Decisions Pending

These should be settled before the relevant implementation phase begins:

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

4. **Where do PDF page metrics live?**
   - `content_artifact.payload_json` (simple, no schema migration, good for v1).
   - Dedicated `content_page_metric` table (better analytics/querying, more schema work).
   - **Tentative recommendation:** artifact JSON for v1; migrate only if analytics needs it.

5. **How aggressively should the platform use external PDF services?**
   - Local-first with external fallback only for scanned/poorly extracted PDFs.
   - Managed parsing for every PDF.
   - **Tentative recommendation:** local-first. This keeps cost and privacy risk low for community-uploaded books.

---

## Out of Scope (for now)

- PDF annotations beyond highlights (freeform drawing, sticky notes, shapes).
- Full OCR implementation for scanned PDFs by default. OCR is now a researched fallback path for `needs_ocr` documents, not a baseline reader requirement.
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
