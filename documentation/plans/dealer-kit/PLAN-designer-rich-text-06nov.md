# PLAN: per-selection formatting in tag designer text layers (DESIGNER-RICH-TEXT, 6 Nov)

Status: Owner hand test fix round (in-place canvas formatting, selected chip); right-click/Group PASS. Full track by size (about 1,600 changed lines, over the ~300-line small
fix limit), though frontend only: no migration, no auth/RBAC, no new ingest, so no
security-reviewer. PR #2213.
UAC: `designer-rich-text-acceptance-criteria.md`.

Owner ask (6 Nov ~10:30): a Text layer's Content can only be styled as a whole. Selecting
`{{product.code}}` and pressing Cmd+B bolds the whole box. He wants bold / italic / underline /
strike / colour per selection inside one text box, with Insert field still working and tokens kept
atomic.

Owner bug folded in (6 Nov, same canvas code): right-click on a multi-selection replaces it with the
frame layer, so Group is never enabled; the context menu shows `Ctrl+` on macOS.

## What already existed (measured on main 578ef86c)

- One rich renderer for canvas, preview and print: `lib/dealer-kit/product-block.ts`
  `layerRichBlocks` -> `richBlocksWithFields`, parsing with `lib/dealer-kit/rich-text.ts`
  `parseRichText` and resolving `{{tokens}}` per run (a token's value already inherits its run's
  marks). Canvas: `layerDisplay` -> `KonvaTagLayer` `RichTextContent`. Print:
  `TagSheetRenderer.tsx`. Until now only data (descriptions, #2180) reached it as HTML.
- Layer content: `props.text` (unbound) / `text_override` (bound), plain string, edited in a
  textarea in `InspectorPanel.tsx`.
- Shared editor: `components/ui/rich-text-editor.tsx` (TipTap).

## Decisions

- D1. Reuse the shared editor with two opt-in props: `toolbar="inline"` (bold, italic, underline,
  strike, colour; named "... selection" so they do not clash with the layer's own whole-text
  Bold / Italic toggles below) and `mergeFields` (`components/ui/rich-text-merge-fields.ts`: a
  `{{path}}` token is one inline atom node; value in and out keeps plain `{{path}}` text).
- D2. Storage is back-compatible (`lib/dealer-kit/layer-content.ts`): content with no formatting
  is stored as today's plain text, one line per paragraph; only formatted content is stored as
  HTML. No migration; existing templates load and render unchanged.
- D3. Layer-level font / size / weight / colour stay the default; inline marks override per run.
- D4. A rich data token (`{{product.price_tag_description}}`, `{{combo.description}}`) inside
  formatted layer text is spliced in as the data's own blocks. Crew ruling (a), 6 Nov: union, the
  description keeps every mark set on the product / combo page; the token's marks are only the
  default for unmarked text.
- D5. Owner hand test 6 Nov (supersedes the read-only interim): the canvas in-place editor is the
  same rich model as the Inspector's Content box (shared editor, `toolbar="none"`, `mergeFields`,
  stored through `contentFromEditorHtml`), so Cmd+B / I / U on a canvas selection marks only that
  range and the layer-level weight is untouched. Its plain read-only modes stay: a sole token
  previewing its resolved value, a description slot (R16). The spec sheet reader page (embedded
  canvas) keeps its plain typing-over box. Clipboard words, Layers panel names and preview labels
  read plain text.
- D7. Owner hand test 6 Nov: a token chip inside the selection (drag across it, or a click on it)
  carries `merge-field-selected`, drawn in the selection colour with a ring.
- D6 (owner bug). Right-click keeps the selection when ANY selected layer is under the pointer,
  even below unselected layers drawn on top of it (a frame, a card; crew pass item 12 ruling, which
  supersedes review S3's "drawn layer decides"); otherwise the layer Konva actually hit is selected
  alone (the top box when Konva reports none); empty canvas keeps the selection. Cmd+click
  (macOS) / Ctrl+click (elsewhere) is additive; a macOS Ctrl+click never changes the selection.
  Menu shortcuts and toolbar tooltips use the command symbol on macOS.

## Not built

- Server-side sanitising of layer HTML: no renderer writes it into the DOM (parsed with
  `DOMParser` and walked, as #2180 established), and the editor parses it through its schema.
  Trigger to revisit: any new consumer that would render layer text as HTML.
- Escape while the canvas context menu is open still reaches the canvas Escape handler
  (deselects). Existing behaviour, not part of this ask.
- Owner bug #2 (Shift+click picking up extra layers) was retracted by the owner as a misreport;
  nothing built for it.
