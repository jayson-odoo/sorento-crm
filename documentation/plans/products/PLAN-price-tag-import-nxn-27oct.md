# PLAN: price tag import, dimension spacing and line order count as the same text

Status: Review complete (reviewer READY round 2 on 876c19a7); awaiting CI, merge and owner re-run of the import. Track: small fix (script only, no migration, no auth). Lane: PRICE-TAG-IMPORT-NXN.

## Problem

Owner ran `sorento_crm_backend/scripts/import_price_tag_descriptions.py` on prod with
`Sorento_Lite_DIY_Catalog_Product_Codes.xlsx`: updates 0, unchanged 148, skipped 28, all
"same code on several rows with different text".

`format_key` (scripts/import_price_tag_descriptions.py:141) evens out spacing, `:` and case, but
`150x150` and `150 x 150` still differ, so 24 floor-trap codes (SRT6531-DIY and family) conflict.
`dedupe` (:148) keeps a text only when it contains every other one. Of the 4 kitchen taps, 3 print
the same lines in a different order; SRTKT1933SS-DIY is a real contradiction (Pillar vs Wall).

## Fix

1. `format_key` also writes a dimension product as `NxM`: `(\d)\s*[xX×]\s*(?=\d)` -> `\1x`
   (lookahead so `1 x 2 x 3` chains).
2. `dedupe`: two texts with the same lines (each compared by `format_key`, same counts) in any
   order are format-equal; the first row's text is written. Not for a text with an S-/P-Trap line:
   there order says which trap block a line belongs to (`cut_trap`), so a reorder is a conflict.
3. The skipped CSV already names the sheet rows (`sheet_rows`, and `row N:` per text); a test pins it.

## Tests (red first)

In `tests/test_import_price_tag_descriptions.py`, the three real shapes:
spacing (`150x150` vs `150 x 150`, and `x`/`X`/`×`), order (same lines reordered), contradiction
(Pillar vs Wall stays skipped, with both sheet rows listed). Plus: a longer text with an extra
`Gunmetal` line still wins over the bare one after dimension normalisation.
