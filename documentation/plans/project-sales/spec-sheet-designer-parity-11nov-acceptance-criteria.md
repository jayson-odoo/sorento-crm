# UAC: spec sheet designer parity, slice A

Plan: `PLAN-spec-sheet-designer-parity-11nov.md`.

- AC-A1: a spec sheet page's "Add accessory" option reads the product code once when the name
  equals the code, and "CODE Name" otherwise (shared `codeWithName`).
- AC-A2.1: on the spec sheet, Cmd/Ctrl+C, X, V, D, Delete, arrows and Cmd/Ctrl+Z act on the page
  holding the selection (else the page being read), and on no other page.
- AC-A2.2: a layer copied on one page pastes onto another page at the same x/y; on the same page
  it pastes offset like a duplicate (same rule as the price tag designer).
- AC-A2.3: an image on the OS clipboard pastes as an image layer through the existing asset
  upload (PNG/JPG/WebP/SVG, up to 20 MB), on the active page.
- AC-A2.4: in both designers, the context menu's Paste is enabled with nothing copied in the
  editor and pastes the system clipboard (picture, words, or the editor's own copied layers).
- AC-A2.5: a read-only page answers no shortcut and no paste.
- AC-A3: the spec sheet's Pages and Inspector panels resize by dragging, with the template
  designer's limits, and the widths persist in the same per-browser setting as the template
  designer's.
- AC-A4: Insert field offers Product > Description = `{{product.description}}`, the product
  master's plain description, on price tag templates and spec sheet pages (line and parts).
