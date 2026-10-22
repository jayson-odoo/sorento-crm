# PLAN: SEAT-COVER-HIDDEN (23 Oct)

Status: in review, PR #1832 (small fix track: backend only, no migration, no auth change)

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
2. Crew answer (b), 23 Oct: #1710 AC-19 stands. A WC whose links are all hidden still runs on
   as typed (no line, no "no seat cover on record" claim); with fix 1 that is the bare WC code,
   no file ask. The owner moves the hidden cover's category in data.
3. Family code (SRTWC8840, no exact product; variants SRTWC8840-LID / -SC). Under existing rules:
   - `find.py:296-303`: a typed code that is no product's is read as the linked SKUs holding it
     (`_linked_codes_holding`, `find.py:135-170`) only when those SKUs sit on a link. The live
     reply (a variant picker) shows they do not, so the code is `unknown`.
   - `find.py:352-357` (card Q3 a): an unknown code runs on as typed, to the resolver's own
     picker; `resolve_gate.py:726-727` keeps the typed code (`keep_typed_codes`) on a find turn.
   - The picker turn names a code of its own, so `engine.py:5197-5201` leaves no relation on the
     focus: the customer's pick answers that variant plainly, with no fit line. No existing rule
     carries a fit ask through a variant picker; building one is a new rule (trigger: an owner
     ask). SRTWC8840-SC is itself a seat cover by the data (`is_spare_seat_cover`).
   - What was wrong live is only the file annotation ("no Product Photos / has Product Photos"):
     the relation's word rode along as a photo type. Fix 1 removes it, so the picker is the bare
     family code's picker (`test_the_family_turn_is_the_bare_family_code_turn`).

## Tests

`tests/chatbot/test_seat_cover_hidden.py`: hidden cover (as typed, no file ask), no-link WC, fits + file entity
(installation guide / certificate / photo), visible cover control.
