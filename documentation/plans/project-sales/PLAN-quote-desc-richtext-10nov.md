# PLAN: QUOTE-DESC-RICHTEXT (rich text line description on proposals / quotations)

Status: Merge-ready pending owner hand test (reviewer + security READY, fix round done). Track:
LEAD pattern, size M. No migration, no auth / RBAC change. PR #2304.

Owner ruling, 10 Nov ~14:30 MYT: "the description should use rich text editor also to allow styling".
Behaviour card (rules, readers table, questions): `CARD-quote-desc-richtext-10nov.md`.

## Slices

1. Server save rule: `app/utils/tag_rich_text.py` `sanitise_description` (rich -> price tag allow-list; plain kept
   as typed; unstyled edit -> plain lines; empty -> null). Called once in `_write_line`
   (`services/project_quotation_service.py`), which every line write path goes through.
2. PDF: `_description_html` in `services/project_quotation_pdf_service.py` re-sanitises and wraps styled text in
   `<div class="rt">` for both the plain and the matrix scope tables; `.rt` CSS keeps paragraphs tight.
3. Plain readers: `line_text(line)` in `project_quotation_service.py` (= `plain_text`), used by Excel, price-change
   alert, amendment feedback rows, SO draft (both component paths), PO check, sample request, spec sheet, the
   re-ask report label. Guard test: no other module reads `description_snapshot` raw.
4. FE: `components/common/RichDescription.tsx` (plain as typed, styled via `RichTextView`, never innerHTML);
   `QuotationLinesGrid.tsx` DescriptionCell = trigger + popover with the shared `RichTextEditor` (full toolbar);
   labels / line search read plain (`richOneLine` / `richPlainText`); sign page `QuotationSignScopes.tsx` draws
   `RichDescription`, feedback label plain.

## Tests

- `sorento_crm_backend/tests/test_quotation_line_description_rich.py`
- `QuotationLinesGrid.description.test.tsx`, `QuotationSignScopes.richDescription.test.tsx`

## Evidence (sandbox, 10 Nov)

- Backend: lane file 21 passed; 84 neighbouring files 1724 passed, 1 skipped; PDF/Excel/lines/tag-rich 248 passed.
- Frontend: touched suites 326 passed; project-sales + sign + rich-text sweep green; tsc and eslint clean on touched files.
- Kill tests K1-K9 red (K9 line search test added in the fix round).
- Real WeasyPrint PDF: bold, colour, heading, italic, underline, strike, highlight, bullets, numbering, right
  alignment all print; plain two-line description prints as before; a very long styled text wraps in its column.
- Browser (Playwright, sandbox stack): sign link at 1280 and 375 draws bold + red from the parser, no page overflow.
  The staff Lines tab threw "Rendered more hooks than during the previous render" in Next's Router on the sandbox
  stack with main's own code too, so the grid browser pass is left to the owner hand test (jsdom covers it).

## Feedback round 1 (owner hand test, 10 Nov)

- Owner: "for me to click twice to be able to edit the description is quite not user friendly". Now one step: the
  click on the cell opens the shared editor (full toolbar) with its caret at the clicked character (click point read
  as a text offset, `quotationDescriptionCaret.ts`, list markers marked `data-rt-marker` in `RichTextView`); Tab into
  the cell, Enter or Space opens it with the caret at the end; Escape closes and the returning focus does not reopen.
- Crew pass on 7ea1d6efc: plain text of a list put the marker on its own line ("• \nbullet one") in Excel, WhatsApp
  and notifications; `_PlainText` now continues the marker's line (`tag_rich_text.py`).

## Feedback round 2 (owner hand test 16:42 + crew re-pass on 6b7c3dac)

- Colour picker closed mid-pick: the toolbar's colour button applied with `editor.chain().focus()`, and that focus
  move counted as focus outside the colour popovers. Now applied without moving focus (`rich-text-editor.tsx`
  `ColorPopoverButton.apply`; the price tag editor shared the bug and gets the fix).
- Hue click applied black: with no colour set the picker starts at #000000, and a hue on black stays black. A hue
  picked on black / white / grey now takes full saturation and brightness (`ColorPicker.tsx` `withHue`).
- Esc reopened the editor ~1 s later: the 100 ms reopen guard expired before the close animation handed focus back to
  the cell. The guard now holds until that focus arrives, or until focus / a press lands anywhere else.
- Real Chromium check (throwaway harness page, not committed): one click puts the caret after the clicked word; hue
  and map presses keep all popups open and apply the colour; Esc peels picker, colour popover, editor in turn and the
  editor stays closed; a click outside closes it; Tab back into the cell opens it.
