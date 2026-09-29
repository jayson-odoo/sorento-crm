# PDF viewer search and zoom: browser evidence (26 Sep 2026)

PR #1256 fix round 2, from the owner hand test on :3083 (26 Sep, head a436d1534): search inside
the viewer, and zoom with the wheel, keyboard and cursor like a normal PDF viewer.

Component-level, not a full stack run, the same setup as `../themed-pdf-viewer-25sep/`: a
scratch page (not committed) rendered the real shared `PdfViewer` beside a stand-in lines card
in the PO Documents tab split, and the real `AttachmentPreviewModal`, on the repo fixture
`e2e/fixtures/project-cs/quotation-qt-004188.pdf` (4 pages, real text). Chromium 1194 on
`npm run dev` (Turbopack), driven with agent-browser 0.27.0 using real key presses.

| File | What it shows |
| --- | --- |
| `search-light-1280.png`, `search-dark-1280.png` | Ctrl+F on the focused viewer opened the search row with the box focused; "sorento close" matched across text items, every match painted, the current one outlined, "2 of 4" |
| `search-last-match-light-1280.png` | Shift+Enter wrapped from match 1 to 38 of 38; the viewer moved to page 4 and the match sits inside the view |
| `search-no-text-light-1280.png` | a scan with no text layer (a drawn-only PDF): "No searchable text in this PDF" |
| `zoom-wheel-cursor-light-1280.png` | three Ctrl+wheel notches at the word "QUOTATION": 121% to 221%, the word still under the cursor, pages re-drawn sharp |
| `search-zoom-light-375.png`, `search-zoom-dark-375.png` | 375px: toolbar wraps by group, search row fits, Ctrl+= zoomed to 66%, the zoomed page scrolls sideways inside the viewer only |
| `modal-search-light-375.png` | the attachment preview modal at 375 (also reached from RevisionTimeline and My Downloads) with the search open |

Measured in the same run:

- Ctrl+wheel around a word: the word's position moved 0.05px across, 0.17px down (121% to 221%).
  The canvas bitmap was 1352px wide for a 1352px page: re-rendered at the new scale, not stretched.
- Real input (Playwright's mouse wheel, since agent-browser's `mouse wheel` never reached the
  page in this headless setup): a plain wheel scrolled 600px with the zoom unchanged; eight small
  Ctrl+wheel deltas, the way a trackpad pinch arrives, zoomed 124% to 158% with the word under
  the cursor within 0.7px.
- Ctrl+-, Ctrl+=, Ctrl+0 on the focused viewer: 221% to 177% to 221%, then back to fit width (121%).
- Esc in the search box closed the search, cleared the highlights and put focus back on the
  pages. In the modal the first Esc closed only the search; the second closed the dialog.
- `documentElement.scrollWidth` stayed 375 at 375px, zoomed in.
