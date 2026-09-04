# PLAN: Kailu-shape packing list uploads (G3a)

Status: Implemented (branch `fm/scm-kailu-packing-list-reader`; migration 375, tests green, reviewed)

## Diagnosis against the real file

File: `Sorento装箱单（凯路）260717.xls` (legacy BIFF, 1 sheet `总表`, 25 rows).
Header on row 3 (`No. / 型号 / 货名 / 材质 / 数量 / PCS/CTN / 箱数 / 包装规格cm / CBM/CTN /
体积 / NW / GW / TOTAL KGS / 总毛重 / 牌子/LOGO`), sub-header row 4 (`L W H / KG / NW GW`),
data rows 6-22 (17 lines), totals row 25 (qty 3419, cartons 256, cbm 8.36007025).

Of the three suspected causes, exactly ONE stopped the upload:

1. **Missing aliases - the real blocker.** With only migration 311's seeds the reader
   resolves no `item_code`/`qty` column (`型号`, `体积`, `货名`, `牌子/LOGO` are unseeded;
   `normalize_header('体积') != normalize_header('体积(cbm)')`). Preview returns
   `missing_columns=['item_code','qty']`; the dialog reports "This file has no item_code,
   qty column."
2. **Two-row header - NOT a blocker.** The sub-header row resolves no aliases, so it never
   reads as a header (`_is_header` needs item_code AND qty) and never reads as a line (no
   item code). It falls through today's reader untouched. Proven by parsing the real file:
   17 lines, correct totals, totals row excluded. No reader change.
3. **Legacy `.xls` - already supported.** `upload_intake.allowed_extensions()` default is
   `xlsx,xlsm,xls`; `sheet_rows` dispatches OLE2 magic to xlrd; the FE dialog's accept list
   comes from the server (fallback already `.xlsx,.xlsm,.xls`). Not the failure.

The known `bl_no='Date 日期：'` defect is NOT in this file's path: it carries no `提单号`
label at all, and `Date：2026-07-17` resolves no alias. Untouched.

## Change

1. **Migration `375_kailu_packing_list_aliases`** (mirrors 357's shape: `_ALIASES`,
   importable `seed(bind)`, idempotent `ON CONFLICT DO NOTHING`, exact-row `downgrade`).
   Read fields:
 - `("packing_list", "item_code", "型号", "zh")`
 - `("packing_list", "product_name", "货名", "zh")`
 - `("packing_list", "cbm_total", "体积", "zh")` (per line: cartons x CBM/CTN; the
     reader derives cbm_per_unit = total/qty itself)
 - `("packing_list", "brand", "牌子/LOGO", "zh")`
   Resolved-and-deliberately-not-read (357's "cried wolf" mechanism, so the unmapped
   warning stays meaningful): `No.`→row_no, `材质`→material, `PCS/CTN`→pcs_per_carton,
   `包装规格cm`→packing_dim, `CBM/CTN`→cbm_per_carton, `NW`→carton_net_weight,
   `GW`→carton_gross_weight, `TOTAL KGS`→total_net_weight, `总毛重`→total_gross_weight.
   (NW/GW are per-carton on this file - aliasing them to net_weight/gross_weight would
   store carton weight as line weight, so they stay unread.)
2. **`scripts/bootstrap_env.py`**: replay the new migration's `seed()` exactly as 338/357/358
   are replayed (create_all databases never run migration bodies).
3. **Tests** (`tests/scm/`): real file committed as fixture
   `tests/scm/fixtures/kailu_packing_list_sample.xls`; reader test parses it end to end
   (1 block, 17 lines, qty 3419, cartons 256, cbm sum 8.36007025, per-line spot checks,
   verbatim item codes including the embedded-newline `SRTWT8258\n-GM`, totals row and
   sub-header row excluded); alias-seed test proves `seed()` rows resolve the real headers.
4. **No reader change, no FE change.**

## Out of scope (other lanes)

Multi-supplier containers / consolidated list (PR #208), proforma invoices/prices, fuzzy
item-code matching. Item codes persist verbatim; `SRTWC286-SH-200NEW` style mismatches with
the catalogue stay unmatched by design (named in preview, line skipped on apply).
