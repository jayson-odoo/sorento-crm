# UAC: DESIGNER-RICH-TEXT (6 Nov)

Plan: `PLAN-designer-rich-text-06nov.md`.

## Per-selection formatting

- AC-1. Inspector > TEXT > Content is the shared rich editor with Bold / Italic / Underline /
  Strikethrough / colour buttons that act on the selection; Insert field stays beside it.
  Test: `InspectorPanel.richContentEditor.test.tsx`, `rich-text-editor.mergeFields.test.tsx`.
- AC-2. A `{{token}}` is atomic: a selection covering part of it formats the whole token; it is
  never split. Insert field inserts at the caret. A typed `{{path}}` becomes a token.
  Test: `rich-text-editor.mergeFields.test.tsx`.
- AC-3. Formatting writes rich HTML to the layer (`props.text`, or `text_override` when bound);
  an edit with no formatting keeps plain text. The layer's font / size / weight / colour stay
  the default. Test: `layer-content.test.ts`, `InspectorPanel.richContentEditor.test.tsx`.
- AC-4. Canvas and print draw the runs; a value substituted into a token inherits that token's
  marks. Test: `product-block.layer-rich.test.tsx` (canvas blocks + `TagSheetRenderer` spans).
- AC-5. A rich description token inside formatted text keeps the description's own marks; the
  token's marks fill only unmarked text (crew ruling (a)). Test: `product-block.layer-rich.test.tsx`.
- AC-6. Existing plain templates render unchanged; plain readers (Copy rendered text, Layers
  panel name, clipboard words, preview label) never show markup.
  Test: `product-block.layer-rich.test.tsx`, existing dealer-kit suites.

- AC-10 (owner hand test 6 Nov). Double-click a text box on the canvas, select only line 2
  (`{{combo.description}}`), Cmd+B: only that line is bold, in the canvas and the Inspector; the
  layer-level Bold stays off. Same for Italic / Underline. Unformatted in-place typing stays plain.
  Test: `TagCanvasEditor.inPlaceRich.test.tsx`; real Chromium run (Playwright, not committed).
- AC-11 (owner hand test 6 Nov). A selected token chip looks selected (selection colour + ring)
  whether it was clicked or dragged across; a chip outside the selection does not.
  Test: `rich-text-editor.mergeFields.test.tsx`; real Chromium run.

## Right-click and shortcuts (owner bug)

- AC-7. Two text boxes selected, right-click where one of them lies, even under a frame or card
  drawn on top of it (filled or not): both stay selected and Group is enabled. Any selected layer
  under the pointer wins over unselected layers drawn over it (crew pass item 12, 6 Nov).
  Test: `TagCanvasEditor.context-selection.test.tsx`, `canvas-input.test.ts`.
- AC-8. Right-click where no selected layer lies selects just the layer Konva drew there (the top
  box when Konva reports none); on empty canvas the selection is kept.
  Test: `TagCanvasEditor.context-selection.test.tsx`, `canvas-input.test.ts`.
- AC-9. macOS: Cmd+click adds to the selection, Ctrl+click (system right-click) leaves it alone,
  Cmd+G groups, the menu shows `⌘X ⌘C ⌘V ⌘D ⌘G ⌘A`. Elsewhere `Ctrl+`.
  Test: `canvas-input.test.ts`, `TagCanvasEditor.context-selection.test.tsx`.
