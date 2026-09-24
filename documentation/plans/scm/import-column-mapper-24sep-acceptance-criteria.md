# UAC: inline import column mapper, remembered per supplier

Plan: `PLAN-import-column-mapper-24sep.md`. Status: GRILLED 24 Sep (R1-R5, G1-G5).

## Journey

Purchasing staff opens Loading plans > Plan a container (or Proforma invoices > Upload
supplier documents), picks the supplier, drops the supplier's file. The system reads the
sheet, finds the table header row, and shows each column with two sample values. What it
already knows for this supplier is pre-filled. First time for a layout: the user picks a
field for each column that matters and Ignore for the rest (one decision per column),
then Test. Test saves the layout and reads the file; the verdict shows lines, qty, total.
Confirm creates the PI / starts the plan as today. Next file from that supplier: the
mapper is folded to "N of N columns mapped from saved layout", Test is live at once; it
unfolds only when a column the system has never seen appears. Nobody is told anything
automatically; the admin page lists what was saved, per supplier.

## Probe and readers

- AC-M1 Uploading any of the four sample files finds the table header row without any
  alias configured (rows 14, 15, 15, 2) and lists every column with its full header text,
  line breaks included, and up to two sample values from the first non-blank data cells.
- AC-M2 A column with no header text under a merged header is listed as `<parent> [n]`
  (`外箱/木托尺寸 [2]`); a second header row under a merged parent is spliced into the
  parent (`箱子 CTN SIZE (CM) L (长)`). Both are mappable and resolve on the next upload.
- AC-M3 The user can move the header row up or down; the columns and samples re-read.
- AC-M4 When required fields are unresolved, the preview still names every unresolved
  column (no more empty "columns not recognised" while "qty missing").

## Memory

- AC-M5 Saving a mapping writes supplier-scoped rows; the same header uploaded by another
  supplier is unaffected; a shared row with the same header is overridden for this
  supplier only.
- AC-M6 Re-mapping a header for the same supplier replaces the earlier choice; rows never
  accumulate.
- AC-M7 Ignore is a saved choice; an ignored column counts as known and never reaches the
  reader.
- AC-M8 Stock list (`supplier_inventory`) columns are mappable; the field list carries no
  internal names (`row_number`, `index`, `header_row`, `lines`).

## Dialogs

- AC-M9 Plan a container and Upload supplier documents both show the mapper once a file
  lands, before Test; Test is disabled while a required field is unresolved and the
  disabled reason names the field.
- AC-M10 Test saves the mapping and runs the preview in one click; Confirm uses the saved
  layout and the chosen header row.
- AC-M11 Second upload for the same supplier and doc type with every column known: the
  mapper is collapsed to "N of N columns mapped from saved layout" with a Review toggle,
  and Test is enabled immediately.
- AC-M12 Second upload with one new column: the mapper is expanded with that column
  highlighted; the rest are pre-filled.
- AC-M13 Multi-file upload shows one mapper per file under the file name; a combined file
  shows ONE section whose Save lands under both proforma_invoice and packing_list.
- AC-M16 When no header row is detected the mapper says so, starts the stepper at row 1,
  and Test stays disabled until a header row yields the required fields.
- AC-M14 Every select is `SearchableSelect`, clearable, with an Ignore entry; no UUID and no
  explanatory copy on screen; usable at 375px and 1280px.
- AC-M15 The retired "Map to..." chip is gone; the admin page still lists supplier rows
  with the supplier chip and lets them be deleted, including ignore rows.

## End to end (browser, samples)

- AC-E1 FSCU8706420 as NEW YANGGANG: map `客户型号`->item_code, `总数量（个）`->qty,
  `件数（件）`->cartons, `单价（元）`->unit_price, `金额（元）`->amount, `备注`->remark, ignore
  the rest; Test reads 4 lines, qty 1262, cartons 257, total 220290 (row 20 is the file's own
  合计 total row, not a line); Confirm creates the PI.
- AC-E2 OOLU9610547 next: mapper collapsed, Test reads 3 lines, qty 251, total 79542.
- AC-E3 吕生 stock list via Plan a container: map `客户型号`->item_code, `总数量（个）`->
  qty_packed; Test reads 44 rows (48 data rows on the sheet, row 47 unreadable, blanks skipped);
  Confirm starts the plan.
- AC-E4 DAFUYUAN PI: `单价 (RMB)`->unit_price, `总金额 TOTAL RMB`->amount, spliced L/W/H ->
  carton dims; the sheet names itself 装箱单 and carries cartons + CBM, so Test classifies it
  combined: the PI block reads 15 lines, qty 903, total 110434; the packing block (cartons 744)
  is offered as a draft packing list. One invoice, one draft packing list on Confirm.
