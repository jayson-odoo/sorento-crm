# PLAN: SCM UI feedback batch, 14 Sep 2026 (loading plan, order inquiries, proforma invoice)

Status: BUILDING - owner screenshots 14 Sep, lane `feat/scm-ui-feedback-14sep`, one PR.
UAC: `scm-ui-feedback-14sep-acceptance-criteria.md`

## Journeys

- J1 Buyer on a loading plan's Supplier codes tab types a code fragment or a phrase from
  "Supplier says" and both tables (Needs a decision, Remembered) narrow to matching rows.
- J2 CS on Order inquiries types `SO366990 SRTWT6801` and sees only that product on that
  order; each word narrows further (AND), any word may hit any searchable column (OR).
- J3 Buyer opens a loading plan: the page header holds the title and breadcrumb only; the
  plan's status, dates and stock-list provenance live on a General tab, first in the strip.
- J4 Buyer reads the Remembered table: "Matched to" shows the code only, no "How" column,
  and "By" is always a person's name (or a dash), never a UUID.
- J5 Buyer on a proforma invoice's Lines tab matches a line to a product OR a set from one
  always-on dropdown in the Product column, exactly like the loading plan's Supplier codes
  cell: pick writes the supplier-code alias at once, no Edit/Save, no second "Match" column.
- J6 Buyer on a proforma invoice's General tab sees the source files as the same file card
  the packing list's Related Documents uses (name, type, size, preview, download).

## Measured facts (main ae0831776, two Opus explorers 14 Sep)

- Loading plan page: `app/(protected)/scm/loading-plan/components/LoadingPlanView.tsx`.
  `PageHeader` at 519-551 carries the `Planning` badge (537-541) and the subtitle
  `Started X · up to Y · Stock list Z` (443-451, `data-testid="plan-subtitle"`).
  `DetailActions` (pager + gear + Save) at 553-585. Tabs 588-597, ids `lines|codes|sent`,
  URL-synced via `useUrlTab`. `PageHeader` has no tabs slot.
- PI detail (`scm/proforma-invoices/[id]/components/ProformaInvoiceDetail.tsx`) is the
  pattern: record header Card 1185-1310, tabs 1315-1337, General tab 1339-1455 built from
  Card sections + a local `Field` (98-118) label/value helper.
- Supplier codes tab: `scm/loading-plan/components/SupplierCodesTab.tsx`. No search box.
  Needs-a-decision columns 248-363 (`code`=item_code, `says`=product_name·brand·spec,
  `packed`, `product` SearchableSelect via `fetchProductOrSetOptions`, `dismiss`).
  Remembered columns 365-457 (`code`, `matched_to`, `how`, `when`, `by`, `forget`).
  `matchedToLabel` 75-81 renders `product_code - product_name` (or set_code - set_name).
- "By" UUID: `fulfilment.py:175-181` (`POST /supplier-inventory/apply`) passes
  `actor=current_user.get("id")` into `supplier_inventory_service.apply`, the only call site
  in that router not using `_actor(current_user)` (62-65, name else email). Auto aliases
  written during a stock-list upload therefore carry a UUID in
  `scm.supplier_product_code_alias.created_by` (String(200), free text). Refresh matching
  and the PI upload path already pass a name. Serializer `list_for_supplier`
  (`supplier_code_alias_service.py:478-512`) emits `created_by` verbatim. Reusable
  id-to-name helper: `_actor_names` in `plan_exception_service.py:593-605`.
- Order inquiries search: `order_inquiry_worklist_service.py:694-716`, ONE `%phrase%`
  ILIKE OR-ed across item_code, spo_ref, inquiry_no, SO number, product name/code,
  customer name, project title/code, user name, user email (prefix). Shared by list,
  summary and export routes via `_worklist_filters`. Token-split pattern already in the
  codebase: `marketing_service.py:1424-1434` (split on whitespace, one `filter(or_(...))`
  per token).
- PI Lines: Product cell (559-616) is a `SearchableSelect` over `getProducts` only,
  edit-mode only, sets `productSetId: null` always; the `matched` column (962-1076) shows
  badges + Match / Change / Forget, opening `MatchToProductDialog`
  (`scm/components/MatchToProductDialog.tsx`) which POSTs
  `/api/v1/scm/supplier-code-aliases`. The edit-mode save path ALSO writes that alias
  (`proforma_invoice_service.py:2653 _remember_line_match`), so the two controls are the
  same decision through two doors; the dropdown's only gaps are products-only, no sets,
  Edit + Save required. Loading plan cell: `SearchableSelect` + `fetchProductOrSetOptions`
  + `renderProductOrSetOption`, `value=""`, `onOptionChange` -> `useMatchSupplierCodeInPlace`.
  Forget already exists in the PI file as `useDeferredRowAction({ actionKey:
  'supplier_code_alias.forget', entityType: 'supplier_code_alias' })` (235-241).
- PI Source files: inline `<ul>` at ProformaInvoiceDetail 1416-1456 rendering
  `invoice.source_ref` (a filename string) and `packing.data.file` ({name, uploaded_at}).
  Backend already emits `out["source_files"]` (`proforma_invoice_service.py:3386-3402`,
  from `EntityAttachmentService.list_links("proforma_invoice", id)`) with link id, name,
  type, uploaded_at, download_url - the FE never reads it (0 grep hits) and it lacks
  `attachment_id`, `file_size_bytes`, `mime_type`.
- Packing list card: `procurement-management/packing-lists/components/PackingListDocumentsTab.tsx`
  83-135, hand-rolled: name, `type_name • KB`, eye (`getAttachmentPreviewUrl` ->
  window.open), download (`useDownloadAttachment`), unlink. No shared file-card primitive
  exists in `components/common` (only `LinkAttachmentBrowserDialog`, `AttachmentPreviewModal`).

## Rulings (owner, screenshots 14 Sep; captain's readings marked)

- R1 Supplier codes tab gets a search box (code + "Supplier says").
- R2 Order inquiries search matches product AND order at the same time (token AND).
- R3 Plan status badge + Started/up to/Stock list line move out of the page header into a
  "headers tab". Captain reading: a `General` tab, first in the strip, laid out like the PI
  General tab. Default tab stays `lines`. (Overrides the ADR "metadata in the header" rule
  for this page by owner instruction; flip back is one commit if the reading is wrong.)
- R4 "By" never shows a UUID.
- R5 "Matched to" shows the product/set code only.
- R6 "How" column removed (data stays in the API).
- R7 PI Lines: one dropdown, consistent with the loading plan cell; the Match column goes.
- R8 PI Source files use the same component as the packing list's attachment card.

## Slices

### S1 Supplier codes search (FE only)
`SupplierCodesTab.tsx`: one `ListSearchInput` (same primitive as Order inquiries) above the
Needs-a-decision card, `aria-label="Search supplier codes"`, placeholder
`Search code or supplier description`. Client-side, case-insensitive, whitespace-split
tokens AND-ed; a token matches `item_code` or the "Supplier says" text (product_name, brand,
spec) on the queue, and `supplier_code`, `product_code`, `set_code` on Remembered. Both card
titles show the filtered count (`Needs a decision (12 of 61)` while filtering, plain `(61)`
when empty). Confirm (n) still counts decided rows regardless of filter. Empty result renders
the existing empty state copy with "No code matches".

### S2 Order inquiries token search (BE)
`order_inquiry_worklist_service.py` query branch: split on whitespace, drop empties, one
`filter(or_(<same 11 columns>))` per token (email keeps its prefix pattern). Same code
serves list, summary and export because they share `_worklist_filters`. No FE change:
the placeholder stays as it is (no on-screen explanation of the token rule).

### S3 Loading plan General tab (FE only)
`LoadingPlanView.tsx`: `PageHeader` keeps title + breadcrumb only (badge and subtitle
removed, `plan-subtitle` testid moves with the text). New tab `general` FIRST in the strip
(`General | Lines | Supplier codes (n) | Sent`), default stays `lines`. General tab body =
one Card `Plan` (PI `Field` grid, 2 cols on sm+): Status (Badge, same STATUS_LABEL/VARIANT),
Supplier, Started (`formatDateTimeInMalaysia`), Plan window (`describeWindow`), Stock list
(`plan.document_label`), plus any other plan header fields the payload already carries that
were previously visible (none expected). Move `Field` from ProformaInvoiceDetail into
`components/common/Field.tsx` and import it from both files (one copy).

### S4 "By" shows names (BE)
- `fulfilment.py:175-181`: pass `actor=_actor(current_user)`.
- `list_for_supplier`: for rows whose `created_by` parses as a UUID, resolve in ONE query
  against `users` (name, else email) the way `_actor_names` does; unresolved UUID -> `None`
  (renders as the dash). No migration: the serializer covers rows already on file.
- Remove the wrong "Already a name, never a UUID" comment in SupplierCodesTab (FE cell
  unchanged otherwise).

### S5 + S6 Remembered table (FE only)
`matchedToLabel` returns `set_code` or `product_code` only (`Dismissed` unchanged, dash when
neither). `how` column definition deleted; `howLabel`/`RUNG_LABEL` deleted if nothing else
uses them (keep the `SupplierCodeRung` type).

### S7 PI Lines: one Product control (FE, small BE)
`ProformaInvoiceDetail.tsx`:
- Delete the `matched` column and the `MatchToProductDialog` mount + `codeToMatch` state
  from THIS file (the dialog file stays; the Packing tab still uses it, out of scope).
- Product column, read AND edit mode, for lines with a non-blank `item_code`:
  `SearchableSelect` with `fetchOptions={fetchProductOrSetOptions}`,
  `renderOption={renderProductOrSetOption}`, `placeholder="Search a product or set"`,
  `paginated pageSize={50} size="sm"`, `selectedOption` = current `{value: product_id |
  'set:'+product_set_id, label: product_code | set_code}`, `clearable` only when
  `line.match_id` is set. `onOptionChange` -> `matchSupplierCode({ supplier_id,
  supplier_code: item_code, ...aliasTargetFor(value) })` (the existing
  `useMatchSupplierCode` from `useSupplierCodeAliases.ts`, which already toasts the rebind
  count and invalidates `scm.proforma-invoices`). Clear -> the existing deferred forget
  (`supplier_code_alias.forget`, 5 s reversible countdown rendered in the cell with Cancel,
  DELETE alias on lapse). While the POST is in flight the select is disabled.
- Lines with a blank `item_code` (operator-added rows, before or after save) keep today's
  draft behaviour in edit mode (pick patches `productId` / `productSetId` via
  `isSetOption`, saved on Save); in read mode they show the code or a dash.
- The `matched` / `set_code` / `match_source` badges are gone with the column. `canAdjust`
  still gates the control (read-only text when the user cannot adjust).
- BE: none required (`POST /supplier-code-aliases` + `_rebind` already re-point the PI
  lines). Verify `_rebind` covers the picked line for a code that differs only by case or
  trailing spaces; fix in `_rebind` if not.

### S8 PI Source files card (FE + BE)
- New `components/common/AttachmentFileCard.tsx`: props `{ name, typeLabel, sizeBytes,
  attachmentId, onUnlink? }`; renders name, `type • size`, icon buttons Preview (eye,
  `getAttachmentPreviewUrl` + window.open), Download (`useDownloadAttachment`), Unlink only
  when `onUnlink` given; every icon button has an aria-label/title. `PackingListDocumentsTab`
  renders it (its unlink flow unchanged, passed in as `onUnlink`).
- BE `proforma_invoice_service.py` `source_files[]`: add `attachment_id`, `file_size_bytes`,
  `mime_type`; make sure the packing-list workbook is linked to the invoice the same way the
  PI workbook is (`_link_source_file`) so it appears in `source_files`; if it is not linked
  today, link it at packing upload time and backfill nothing (new uploads only, old rows
  keep showing name + date without buttons via the fallback below).
- FE: `ProformaInvoiceDetail` type gains `source_files`; the Source files section renders
  one `AttachmentFileCard` per entry (no unlink), `typeLabel` = attachment type name, and
  falls back to today's plain rows only for a packing file that has no link.

## Test list (captain)

- pytest `tests/test_order_inquiry_worklist_search_tokens.py`: two-token query returns only
  rows matching both (SO + item), single token unchanged, order of tokens irrelevant, blank
  and multi-space queries are no-ops, summary route honours the same split.
- pytest `tests/test_supplier_code_alias_created_by.py`: stock-list apply writes a name;
  a row seeded with a user UUID in `created_by` lists as that user's name; unknown UUID
  lists as null; a plain name passes through.
- pytest `tests/test_proforma_invoice_source_files.py`: `source_files[]` carries
  `attachment_id`, `file_size_bytes`, `mime_type`; packing upload links its workbook.
- vitest `SupplierCodesTab.search.test.tsx`: box filters both tables, counts update,
  tokens AND, Confirm count unaffected; Matched to = code only; no How header.
- vitest `LoadingPlanView.general.test.tsx`: header has no badge/subtitle; General tab first;
  fields present; default tab lines.
- vitest `ProformaInvoiceDetail.productSelect.test.tsx`: no Match column; pick on a coded
  line POSTs the alias without edit mode; sets pick with `set:` prefix; clear starts the
  countdown; blank-code line keeps draft behaviour.
- vitest `AttachmentFileCard.test.tsx` + PI General renders cards from `source_files`.

## Out of scope
Packing tab Match button (still the dialog); Forget on PI lines beyond the select clear;
Supplier documents pages.
