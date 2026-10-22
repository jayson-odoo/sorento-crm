# PLAN: SEAT-COVER-HIDDEN (23 Oct)

Status: in progress (small fix track: backend only, no migration, no auth change)

## Problem

"seat cover for SRTWC6031-SH-UF": the WC's only seat cover link points at SRTSCBD289-UF, which
`chat_searchable_products()` hides (category SRTPART, is_searchable false). `as_linked_products`
(`app/services/chatbot/lanes/business/find.py`) marks the anchor `unknown` and returns the parse
unchanged, so the parser's stray file entity ("seat cover" tagged as an attachment type) turns the
fit ask into a file ask ("Which kind of file do you need?").

## Fix

1. When the parse carries a said `fits`, the entity whose raw is the fits value is dropped as an
   attachment type, and a `file_word` the parser left empty clears the file ask, whether or not a
   code was replaced (the rule that already ran after a swap).
2. A visible anchor whose links are all hidden answers with the existing no-link line
   (`FITS_NONE_LINE` / `FITS_NO_WC_LINE` and their kind siblings), as a code on no link does.
   AC-19 amended for that case (owner, 23 Oct); a hidden ANCHOR still runs on as typed (AC-22).
3. Family code (SRTWC8840): see the PR body for the diagnosis.

## Tests

`tests/chatbot/test_seat_cover_hidden.py`: hidden cover, no-link WC, fits + file entity
(installation guide / certificate / photo), visible cover control.
