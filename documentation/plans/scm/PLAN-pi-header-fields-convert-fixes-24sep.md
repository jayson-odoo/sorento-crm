# PLAN: PI header fields from one cell, convert-to-packing-list repeat products, source files, async PL download

Status: BUILT 25 Sep 2026, PR open (review round 1 applied); stacked on #1188; awaiting merge go.
UAC: `pi-header-fields-convert-fixes-24sep-acceptance-criteria.md`.
Track: full `/feature`, one lane, one PR, stacked on #1188.

## What the owner found (24 Sep 2026, DAFUYUAN PI sorento装箱单20260922（1）.xlsx, 15 lines, qty 903)

1. PI General tab: BL shows the whole cell `OOLU2339207730 柜号： FSCU9304169 封条号：OOLLGZ7182`; Container "-".
2. Packing list PL-2609-040 after Convert: Container no, Seal no, SO, Consignee, Shipper all "-".
3. Source files card lists the one upload twice.
4. Packing tab "Supplier code" all "-".
5. Convert dialog: 20 rows for 15 lines, total qty 1,484 vs 903; the PL gets 20 shipment lines,
   175 % full.
6. Convert dialog product table needs search; Convert button jammed against the bottom.
7. Two "Convert to packing list" buttons (header + Packing lists tab empty state); keep the header one.
8. Download packing list must go through My Downloads like the complaint PDF.

## Measured (worktree of #1188 = main + mapper; none of this is mapper code)

- `_labelled` (`packing_list_reader.py:335-398`, used by the PI reader at `:567/:595`) reads ONE
  `label：value` pair per cell unless pairs are separated by ` / ` or `／` (`_MULTI_SEP`, `:62`).
  DAFUYUAN separates with spaces; NEW YANGGANG too (`提单号：   柜号：FSCU8706420   封条：OOLLJN6147`).
  `partition("：")` on the first colon makes bl_no = the whole tail. `柜号` is not an alias of
  container_no (only 货柜号 / 箱号 / Container No); bare `封条` is not an alias of seal_no (only
  封条号 / 封签号).
- PI stores `container_ref`, `bl_ref`, `seal_ref`, `consignee_ref` (`models/scm.py:1725-1735`),
  written at `proforma_invoice_service.py:1008-1018`. General tab renders Container + BL only.
- Convert carry (`proforma_invoice_service.py:2002-2043`): seal, BL and consignee are copied ONLY
  when exactly one container is known; the container comes from the packing rows or
  `container_ref`. With the container unparsed nothing carries. Existing ruling (6 Sep):
  `bl_ref` (提单号) lands in the PL's `forwarder_order_ref` = the **SO** field. Shipper is never
  copied. The dialog's "Carried onto the draft: Container - · BL …" line ignores the condition.
- Source files: `invoice.source_files` (attachment links, name = sanitised `original_filename`
  `sorento装箱单202609221.xlsx`) plus a fallback row for `invoice.source_ref` (raw upload name
  `sorento装箱单20260922（1）.xlsx`) shown when the raw name is not among the linked names
  (`ProformaInvoiceDetail.tsx:1197-1204, 1452-1497`). `sanitize_storage_filename` strips `（1）`,
  so the same upload renders twice.
- Supplier code: aliases are `洁厦型号` / `JIEXIA MODEL` only; the sheet has no such column; "-" is
  right. A per-supplier alias via the mapper can fill it later.
- Convert repeat products: `proforma_invoice_packing_service.py:80-86` builds
  `line_by_product = {product_id: line}` over an unordered query, so every packing row of a
  repeated product binds to ONE invoice line (the last); the other lines of that product have no
  rows and fall back as bare lines with `remaining_qty`, counted again. 15 rows (903) + orphan
  lines (581) = 20 rows, 1,484. `convert_to_draft_shipment` (`:1570`, groups at `:1741-1870`)
  does the same, so the PL gets 20 lines. `rebind_packing_rows` (`:202-220`) picks the FIRST
  line instead: two binders, two answers.
- Convert buttons: header `ProformaInvoiceDetail.tsx:1332-1343`; empty-state `emptyAction`
  `ProformaInvoicePackingListsTab.tsx:134-141` wired at `:1558-1561`.
- PL download: `GET /inbound-shipments/{id}/packing-list/export` (`fulfilment.py:1148-1161`)
  builds the xlsx in-request; FE `downloadPackingListExport` -> `saveBlobAs`. Complaints:
  `POST /{id}/export/pdf` -> `DownloadService.create(kind, source_entity_type="complaint")` +
  `enqueue_job(generate_complaint_pdf, queue_name="imports")` (`complaints.py:1466-1508`,
  `tasks/export_tasks.py:43-81`); FE `exportComplaintPdf` + `EntityDownloadsButton`
  (`components/my-downloads/`).

## Rulings

- R-A (owner 24 Sep, confirms 6 Sep): 提单号 is the B/L number; on the PI it is **BL**, on the
  packing list it lands in **SO** (`forwarder_order_ref`). Unchanged.
- R-B (owner 24 Sep): consignee ALWAYS = the PI's company (Sorento). No sheet parsing; the PI
  General tab and the converted PL both show the company name; `consignee_ref` from the sheet is
  ignored for display and carry (kept in the column, unused).
- R-C (owner): second lane; #1188 untouched.
- R-D (owner 24 Sep): header-level fields ARE mapped in the import mapper, now (section F).
- Fix-round rulings (25 Sep): ignore is a known label; note rows never split a document; a
  line whose product has rows elsewhere never falls back; backfill sets scope None + rollup;
  serialize carry reads packing rows; export task verifies its download row and the owner's
  membership; failure text fixed; header-field choices come from the probe.

## Design

### A. Header cell with several `label：value` pairs (BE)

A1 `_labelled`: split a cell on every alias-recognised label, not only on ` / `. Algorithm: find
every position where a known label (any alias of `_BLOCK_FIELDS` for this doc type, normalised)
is followed by `：` or `:`; each segment from one label to the next label is one pair; value =
segment text after the colon, trimmed. A cell with one label keeps today's behaviour. An empty
value (`提单号：` then next label) yields no pair, so first-wins in `_absorb` still picks a later
row's real BL.
A2 Aliases (shared, migration seed): container_no += `柜号`; seal_no += `封条` (both doc types).
A3 PI General tab renders Seal and Consignee alongside Container and BL (same card, same order
as the PL: Container no, Seal no, BL, Consignee).

### B. Convert carries the header fields (BE + FE)

B1 Carry BL (→ SO), seal, consignee whenever the PI states them and the draft is for ONE
container (today's rule) - unchanged, but now reachable because A1 fills the container. Shipper
stays unset (not on the sheet).
B2 R-B: consignee = the PI's company name, always.
B3 The dialog's "Carried onto the draft" line prints exactly what B1 will write (ask the server:
convert preview returns the carry set) instead of echoing the PI fields.

### C. Convert with repeated products (BE + FE)

C1 One binder: packing rows bind to invoice lines by PRODUCT AND ORDER - the i-th packing row of
product X (sheet order) binds to the i-th invoice line of product X (line order). Both come from
the same sheet, so the pairing is the sheet's own. `replace_packing_rows` and
`rebind_packing_rows` share the function. Queries ordered by `row_no` / line position.
C2 `convert_to_draft_shipment` then finds every line with rows; no orphan fallback for a product
that has rows elsewhere. Dialog and PL show 15 lines, qty 903 for DAFUYUAN.
C3 Backfill: a one-off script rebinds existing PIs whose packing rows are bound to a repeated
product's single line (count them first; report the number in the PR). Existing converted PLs
are not touched.
C4 Dialog: a search box over Code / Product (client-side filter, `SearchInput` shared component);
footer sticky with the standard dialog padding; the table scrolls inside.
C5 Remove the Packing lists tab empty-state Convert button; the empty state keeps its sentence.

### D. Source files (FE)

D1 Show the `source_ref` fallback row only when the invoice has NO linked source file. Match on
attachment identity, never on name.

### E. Async packing-list download (BE + FE)

E1 `POST /inbound-shipments/{id}/packing-list/export` -> `DownloadService.create(kind=
"packing_list_xlsx", source_entity_type="inbound_shipment", source_entity_id=id)` +
`enqueue_job(generate_packing_list_xlsx, queue_name="imports")`; task in `tasks/export_tasks.py`
renders via `consolidated_packing_list.build/to_xlsx` and stores the bytes the way
`generate_complaint_pdf` does. The GET export stays for one release (MCP / n8n callers), marked
deprecated.
E2 FE gear: "Download packing list" enqueues and toasts "Added to My Downloads"; a "Download
history" item opens `EntityDownloadsButton entityType="inbound_shipment"`. Same as complaints.

### F. Header fields in the import mapper (BE + FE, R-D)

F1 Probe (`header_probe.probe`) also returns `header_fields`: every `label：value` pair found in
the rows ABOVE the table header row (and in the footer rows below the table), using the same
label split as A1 - a label is any run of text before a full-width or ASCII colon; value = the
text up to the next label. A label cell followed by a value in the next cell (`Date:` | `14/09`)
is one pair too. Shape per pair: `{row, label, sample, field, source}` where `field` is the
resolver's answer for the label (block fields only: pi_number, invoice_date, bl_no,
container_no, seal_no, currency; consignee excluded per R-B) and `source` = supplier / shared /
none. Also `title` cells with no colon are NOT pairs.
F2 Mapper renders a second section "Header fields" under the columns grid, same three cells
(sample = value, label text as-is, SearchableSelect over the block fields + Ignore), same
folded / open rule (a label with no field and not ignored opens the section). Required = none.
F3 Save writes label -> field rows exactly like column rows (same table, same supplier scope,
same `ignore`), so `_labelled` resolves them through `for_supplier` with no reader change beyond
A1. `doc_types` rule unchanged (combined = both).
F4 The readers use the probe's header row and the supplier resolver already (lane 1); A1's split
recognises a label the moment it is mapped, so DAFUYUAN's three-pair cell is split by the labels
the user just mapped (or by the shared aliases A2 seeds).

## Tests (tester writes red first)

Backend `tests/scm/test_pi_header_cells_and_convert.py` (private DB; fixtures = the mapper
lane's four files): H1 DAFUYUAN row 13 -> bl_no OOLU2339207730, container_no FSCU9304169,
seal_no OOLLGZ7182; H2 NEW YANGGANG row 13 -> bl_no None, container FSCU8706420, seal
OOLLJN6147; H3 single-pair cell unchanged; H4 apply writes the three refs; C1 packing rows of a
repeated product bind by order (3 CWCY604 rows -> 3 lines, qty 40/125/12 each on its own line);
C2 convert draft has 15 lines qty 903, no orphan; C3 rebind agrees with replace; B1 PL gets
forwarder_order_ref = BL, seal, consignee (R-B default when none); E1 export endpoint creates a
user_downloads row and enqueues; task writes the file.
Backend F: probe returns header_fields for DAFUYUAN (提单号/柜号/封条号 with samples, plus Date:/PI No.: pairs) and NEW YANGGANG (封条 bare label); save of a label row resolves in `_labelled` via for_supplier; consignee never offered.
Vitest: Header fields section renders, folds when all known, opens on a new label, saves with the columns in one Test; dialog search filters rows; footer visible at 800px height; single Convert button;
source files card one row; carried line reads from the server; gear items.
Browser: DAFUYUAN upload -> PI shows Container/BL/Seal; Convert -> 15 lines, 903, PL fields
filled; Download packing list -> My Downloads.
