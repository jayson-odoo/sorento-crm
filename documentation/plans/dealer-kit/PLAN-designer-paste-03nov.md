# PLAN: paste from the system clipboard into the tag designer (DESIGNER-PASTE)

Status: in progress. Track: small fix track (frontend only, no migration, no auth/RBAC change,
upload reuses the existing `POST /dealer-kit/assets` surface).

## Journey

Owner, 3 Nov: in Dealer Kit > Tag Templates (the `TagCanvasEditor` shared by price tags and
spec-sheet cover/page templates), a designer copies a screenshot or a picture and presses
Ctrl+V / Cmd+V. The picture lands on the canvas as an image layer, ready to move.

## Decisions

- D1. The editor listens for the browser `paste` event on `window` (the keydown for Ctrl+V no
  longer calls `preventDefault`, which would cancel that event). Focus inside an input, textarea,
  select or contentEditable, or the inline text editor, leaves the paste to the browser.
- D2. Order of what a paste means:
  1. clipboard carries the editor's own copy marker (`application/x-sorento-tag-layers`, written
     by the editor's `copy`/`cut` handler) -> existing in-editor layer paste;
  2. clipboard carries an image file -> image paste (D3);
  3. clipboard carries non-empty plain text -> new text layer with that text, centred;
  4. otherwise, if the in-editor clipboard holds layers -> existing in-editor layer paste.
- D3. Image paste uploads through the same `uploadAsset` call as the Image tool's
  `AssetPickerDialog` (kind `decorative`, same accepted types png/jpg/jpeg/webp/svg, same 20 MB
  cap). With exactly one image layer selected, the upload replaces that layer's source; otherwise a
  new image layer is added, centred on the canvas, sized at 96 dpi and scaled down to fit inside the
  canvas keeping the aspect ratio. One `commit` per paste, so one Ctrl+Z undoes it.
- D4. The context-menu Paste item keeps pasting the in-editor clipboard only (reading the system
  clipboard there needs a browser permission prompt).

## UAC

- AC-1 Ctrl+V with an image on the clipboard and nothing selected uploads it and adds one image
  layer centred, fitting inside the canvas, aspect kept.
- AC-2 Ctrl+V with an image while one image layer is selected replaces that layer's image (same
  id, position and size).
- AC-3 Ctrl+V with plain text adds one text layer holding that text.
- AC-4 Paste while focus is in an input or textarea does nothing to the canvas.
- AC-5 Ctrl+Z after an image or text paste removes it in one step.
- AC-6 A file over 20 MB or of another type is refused with a toast, nothing uploaded.
- AC-7 Ctrl+C then Ctrl+V of layers inside the editor still pastes the layers (existing tests).

## Tests

Vitest: `lib/dealer-kit/clipboard-paste.test.ts` (pure classifier + fit maths),
`TagCanvasEditor.system-paste.test.tsx` (wiring through a dispatched `paste` event).
