# PR #1256 reviewer pass evidence (26 Sep 2026)

Screenshots from the reviewer pass on PR #1256 (themed in-app PDF viewer) at head 4f39aee2.

- Built with `next build` (webpack) in a throwaway worktree and served with `next start` on :3100.
  The worktree had one local-only patch: the `export` keyword removed from `mapSettingsFromApi` in
  `app/(protected)/user-management/settings/layout.tsx`, the known build error on main.
- An uncommitted scratch page rendered the real `POIntakeDocumentViewer` and the real `AttachmentPreviewModal`.
- Driven with agent-browser 0.27.0 on Chromium.
- Fixtures: `e2e/fixtures/project-cs/customer-po-buimaco-r1.pdf` (10 pages, every page `/Rotate 270`)
  and `quotation-qt-004188.pdf` (4 pages, not rotated).

| File | What it shows |
| --- | --- |
| `po-light-1280.png`, `po-dark-1280.png`, `po-light-375.png`, `po-dark-375.png` | PO Documents viewer. At fit width a horizontal scrollbar shows, because the rotated text layer is wider than the page |
| `po-jump-p3-light-1280.png` | A line's note on page 3 opens page 3 |
| `modal-light-1280.png`, `modal-dark-1280.png`, `modal-light-375.png`, `modal-dark-375.png` | AttachmentPreviewModal, `fileActions={false}` |
| `modal-xorigin-light-1280.png` | An item with only a url, served from another origin with no CORS headers (the shape `/view/complaint` and `/view/stock-inquiry` send). It lands in the error state |
| `err-light-1280.png` | A malformed PDF and a password PDF, both in the error state |
