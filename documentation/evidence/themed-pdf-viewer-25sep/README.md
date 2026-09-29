# Themed PDF viewer: browser evidence (25 Sep 2026)

Component-level evidence, not a full stack run: no `sorento_cagent_stack` was available in
this cloud lane, so a scratch page (not committed) rendered the real
`POIntakeDocumentViewer` beside a stand-in lines card, in the same 38% / flex-1 split the PO
Documents tab uses, on the repo's own fixture `e2e/fixtures/project-cs/customer-po-buimaco-r1.pdf`
(10 page scan). The modal shots render the real `AttachmentPreviewModal` on
`quotation-qt-004188.pdf` (4 pages, real text). Chromium 1194 via the dev server (Turbopack).

| File | What it shows |
| --- | --- |
| `po-before-light-1280.png`, `po-before-dark-1280.png` | main: our page bar above the browser's own PDF viewer (dark toolbar, thumbnails, second page count). Taken headed (xvfb), since headless Chromium hides that toolbar. |
| `po-after-light-1280.png`, `po-after-dark-1280.png` | this branch: one toolbar in our tokens, pages drawn to canvas, continuous scroll |
| `po-after-jump-page2-1280.png` | a line's "Page 2" button jumps the viewer to page 2 (the `page` prop) |
| `po-after-light-375.png` | 375px: the toolbar wraps by group, nothing clips |
| `modal-after-light-1280.png`, `modal-after-dark-1280.png`, `modal-after-light-375.png` | attachment preview modal (also reached from RevisionTimeline and My Downloads): header keeps Open/Download, viewer adds pages and zoom only |
| `text-after-keys-1280.png` | after PageDown and `+` on the focused viewer |

Scripted checks in the same run: pdf.js worker loaded from `/_next/static/media/pdf.worker.min.*.mjs`
(same origin); 1059 text-layer spans on the quotation, a double-click selected "SORENTO";
PageDown moved "Page 1 of 4" to "Page 2 of 4"; `+` zoomed 75% to 94%; zero console errors.
