# PLAN: Certification tab UX (CERT-TAB-UX)

Status: Merge-ready pending crew browser re-check and owner hand test (PR #2333); reviewer READY after round 2 (crew browser pass fixes). Track: small fix track by shape (no migration, no auth/RBAC change, no new ingest), size M. UAC: `cert-tab-ux-11nov-acceptance-criteria.md`.

Lane: CERT-TAB-UX. Owner feedback 11 Nov 2026 ~15:10 MYT on the Certification tab built by QUOTE-CERT-TAB (#2245).

## Owner ask (gist)

1. Tab loads slowly: measure, fix, list visible < 1 s at 34 certificates.
2. One line per row; certificate number only, description in a tooltip.
3. Search + multi-select filters (Scheme, Validity, Rows marked, Source) + sorting.
4. Box editor: no "Remove box" button; select + Delete/Backspace, right-click context menu Delete.
5. "Go to box" in one click from the list row and the right panel product entry.
6. Save is the page's obvious primary CTA with unsaved/saved state (or the system's designer auto-save).
7. "Suggested, check": explain, recommend, ask the owner before changing the state model.

## Owner rulings (11 Nov 2026, ~15:55 MYT)

- (a) "yeah drop it": no Suggested state. A box found by a code the system read (`ai`) is just
  Marked: no badge, no Confirm tick; the pencil stays to fix a wrong code. Only rows that need a
  person carry a status (Code not found, Code needed, No text, draw the box).
- The Rows marked filter offers exactly: Marked, Edited, Code not found, Code needed, No text, No file.

## Findings

### 1. Performance

Measured on a seeded 34-certificate quote (one product per certificate; a third typed codes, a
third readable codes, a third not printed), `tests/test_quotation_certificates_perf.py`:

| | Before (main) | After |
|---|---|---|
| Warm list, SQL statements | 79 | 13 |
| Warm list, in-process | 94 ms | 37 ms |
| Warm list over HTTP, same cloud stack (local Postgres) | ~135 ms | ~55 ms |
| List API from the browser (through the Next proxy) | n/a | 50 to 78 ms |
| Cold first look over HTTP (reads + parses 34 files) | n/a | ~310 ms |

Causes found:

- N+1: `Certificate.current_revision` and `CertificateRevision.attachment` loaded lazily, two
  SELECTs per certificate (`quotation_certificate_service._groups`). Fixed with `selectinload`
  (`_with_file`). In production each statement is a round trip to the remote database, so the 66
  removed statements are the bulk of the saving.
- `GET .../certificates` was `@heavy` (`app/utils/heavy_work.py`): one heavy request per worker at a
  time, so the list queued behind any PDF export, spec-sheet render or certificate file read on
  that worker. A warm list does no PDF work, so the route is no longer heavy. A cold first look still
  reads each file once per revision (then cached on `certificate_products.boxes`); `list_rows` now
  releases each file's bytes after its row, so one list holds one file at a time
  (`test_perf_a_cold_list_holds_one_file_at_a_time`). Detail, file and box-save routes stay heavy.
- PDF text extraction does NOT run on every load: the cache from QUOTE-CERT-TAB already holds
  (warm list reads no file, asserted).

The in-browser click-to-rows time on the cloud dev server was ~1.0 s, almost all of it Next dev
compiling the route's RSC payload (absent in a production build); the data itself is ~50 ms.

### 2-3. List

`QuotationCertificatesList.tsx`: one line per row (title and "Also filed as" moved to the number's
tooltip, Rows marked one line, no badge line). Standard `DataGridListToolbar` (search, custom
filters with `SearchableMultiSelect`, active-filter chips, Columns). Client-side sorting on every
column (`PanelDataGrid sortable`), consistent with other detail-tab panels: a tab holds one quote's
rows and is not server-paged. Page size 50 so a 34-row quote is one page.

### 4-6. Box editor

- Delete: the "Remove box" button is gone. Select + Delete/Backspace (existed), plus a right-click
  menu with Delete on each box, using the shared `components/ui/context-menu.tsx` (also used by
  `TagCanvasEditor.tsx`). A Delete key pressed inside the open menu is ignored by the page listener.
- Go to box: the reader opens at the first box in reading order (so a list row click is one click
  to the box), and each product in the right panel has a "Go to box" icon button. The viewer's own
  scroller centres the box (never the window, so the header stays on screen) and the box is outlined
  for 1.6 s with a static ring (no animation). No zoom change.
- Save: manual "Save boxes" is the header's one primary CTA with "Unsaved changes" / "Saving..." /
  "Saved". Auto-save (spec sheet, `useSheetEditing.ts:10`, 1 s) was considered and not used: every
  box save carries a scope choice ("This quote only" / "Every quote (this product)"), and
  auto-saving each drag into the product defaults would silently rewrite every quote.

### 7. Suggested, check (as found, before the ruling)

`suggest_code` (`certificate_pdf_service.py:311`) guesses the printed code on first read and stores
it as `ai` (`quotation_certificate_service.py:301-304`); a box from an `ai` code made the product and
row `suggested` (`:355`, `:378-379`). The tick confirmed the code (`manual`) and changed nothing
else. Removed per ruling (a): service, types, list, reader and `CoverageCodeEditor` (register too).
The backend `confirm` PATCH body is kept (tested, harmless) with no screen sending it.

### Crew browser pass, 11 Nov (round 2)

- Speed on the dev copy: certificate files missing from storage were fetched again on every list
  load (~150 ms each) and the miss was never remembered (`_Group.file`). Now remembered on
  `certificate_products.boxes` (`missing`, `checked_at`) for the revision, retried after
  `MISS_RETRY` (1 h; storage reports a timeout and a missing file the same way); the box editor reads the file itself (`trust_miss=False`). Seeded 34 missing
  files with 150 ms per storage read: warm list 5174 ms before, 50 ms after
  (`test_perf_a_missing_file_is_remembered_and_the_warm_list_never_calls_storage`). The FIRST look
  at a revision still reads its file once (cold: 5.2 s for 34 missing files at 150 ms); that is
  the one read the cache needs. Making even that free would need a background job filling the
  cache, which is not built (trigger: a report that a first open is slow on real files).
- A product whose box was deleted kept "Marked": product states came from the default cache even
  under a quote override. `_unmark_boxless` now sets `unmarked` ("Not marked") for a product with
  no box naming it, unless a box names no product. Quote-only saves keep `product_ids`.

## Known limits

- A hand-added certificate covering no quoted product (`none`) is in none of the six filter buckets,
  so it is hidden while any Rows marked filter is on (follows the owner's exact list).
- A greyed row (`not_on_certificate`) whose products had no code reads "Code not found", not "Code
  needed" (unchanged CERT-16 rule).
