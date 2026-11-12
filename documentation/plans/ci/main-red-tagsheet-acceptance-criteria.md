# UAC: MAIN-RED-TAGSHEET

- AC-1: `TagSheetRenderer.rich-text.test.tsx` (unchanged) passes 6/6 at the PR head with AND without the optional
  `canvas` package installed.
- AC-2: a rich description laid out with no measure keeps the spaces between words, across a bold/plain run
  boundary, and one line per paragraph with no leading space (`text-lines.no-measure.test.ts`).
- AC-3: printed with no canvas, the escaped `<img onerror>` string shows with its spaces, and the page holds no img
  element and no `[onerror]` attribute (`TagSheetRenderer.rich-text.no-canvas.test.tsx`).
- AC-4: measured layouts are unchanged; a zero-width first word never lets the next word run past the box
  (`text-lines.zero-width.test.ts`).
- AC-5: reverting the fix makes AC-2 and AC-3 fail again (kill proof).
