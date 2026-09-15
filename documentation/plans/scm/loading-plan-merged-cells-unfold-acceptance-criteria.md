# UAC: loading plan merged cells + un-fold

Plan: PLAN-loading-plan-merged-cells-unfold.md

## Reader (S1)

- AC-M1: A stock list whose 品名 cell is merged over rows N..N+2 gives every one of the three
  parsed rows that 品名 text as `product_name`. Same for 商标 (`brand`), 规格 (`spec`) and 备注
  (`remark`) when merged.
- AC-M2: A merged 体积 (cbm per unit) cell fills every covered row's `cbm_per_unit`.
- AC-M3: A merged 空瓷 (`qty_unfinished`) or 包装好库存 (`qty_packed`) cell is counted on the
  anchor row ONLY; covered rows read 0 for that field. The sum over the parsed rows equals the
  anchor value.
- AC-M4: A merged total-cbm cell (体积 total, when no per-unit column exists) is used for the
  anchor row's derived `cbm_per_unit` only; covered rows do not derive from it (they get the
  per-unit fill of AC-M2 when a per-unit column exists, else `None`).
- AC-M5: A row's own non-empty value is never overwritten by a fill; only cells inside a merged
  range, other than the anchor, are filled.
- AC-M6: An unmerged sheet parses exactly as before (existing `read_workbook` tests stay green;
  `test_stock_list_xlsm_upload.py` stays green).
- AC-M7: An OLE2 `.xls` stock list parses as before (no merge info, no error).
- AC-M8: After `apply` on such a file, `supplier_inventory` rows for the covered models carry
  the filled `product_name` / `brand` / `spec`, and the Supplier codes queue
  (`unmatched_for_plan`) shows them in "Supplier says".

## Lines tab (S2)

- AC-F1: The Lines tab renders ONE grid. No element with text matching
  /products held with no open demand/ exists for any row set.
- AC-F2: `has_demand: false` rows appear in that grid, after every ranked row under default
  sort, with the muted styling and blank rank they had in the fold.
- AC-F3: The row count shown by the grid / pagination covers ranked + no-demand rows together.
- AC-F4: Search (AC-N3) filters no-demand rows in the same grid; clearing restores them.
- AC-F5: A typed qty on a no-demand row reaches the record (AC-E3 preserved).
- AC-F6: Browser: on the CHAOZHOU JINBAICHUAN plan (stock list 14/09/2026) the Lines grid
  shows 53 rows across pages (35 ranked + 18 no-demand), no fold line; Supplier codes tab shows
  MWB247 and CGB247 with `盆小孔 · M` / `盆小孔 · C` after re-uploading the stock list.
