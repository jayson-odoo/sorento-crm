# PLAN - proforma invoice as a first-class document (G3b) and prices no longer dropped (G3c)

Status: In progress, 2026-08-17. Branch `fm/scm-proforma-first-class`.
UAC: `scm-proforma-invoice-acceptance-criteria.md` (the contract; this plan serves it).

## Journey (from the UAC)

Ms Tee uploads a supplier's proforma against a chosen supplier; the system reads whichever
of the two real shapes it is, tells her what it holds and in which currency (asking only when
neither the document nor the supplier's price list says), and on Apply persists every invoice
with its priced lines. The same pre-loading list uploaded through the packing-list channel now
keeps the unit price it parsed. See the UAC `Journey` section.

## Why this shape

- The pre-loading list IS five proforma invoices (its title cell says so) and the packing
  list reader already parses `unit_price` / `amount` out of it. So the block reader is
  reused rather than duplicated: the proforma reader parametrises the same block-scanning
  helpers with its own doc type, block fields and line shape.
- Kailu's proforma is a different header row (`编号`, `产品数量`, `单价(元)`, `总价（元）`,
  `其他`) and labelled cells (`货单号：`, `日期：`). One alias doc type (`proforma_invoice`)
  covers both because both are, structurally, "labelled cells above a header row above
  lines" - the packing-list reader's second shape.
- Prices go on BOTH homes: the proforma line (the document of record for a price) and the
  shipment line (`unit_cost` + `currency`, already columns since S3b, so the allocation-time
  cost capture works the day it sees one). Neither path parses a price and drops it.

## Data model

Both tables in the `scm` schema, `CompanyScopedMixin`, mirroring `supplier_inventory` /
`loading_plan` (`app/models/scm.py`).

`scm.proforma_invoice`
- `id` uuid pk; `supplier_id` -> `suppliers.id` CASCADE, NOT NULL
- `pi_number` String(100) NOT NULL (stated, else derived `PI-<stem>-<index>`)
- `invoice_date` Date NULL; `currency` String(3) NULL (NULL only when no line is priced; a priced document is refused before write unless it resolved)
- `container_ref` String(100) NULL; `bl_ref` String(100) NULL
- `total_amount` Numeric NULL (the document's own total when it states one, else sum of lines)
- `line_count` Integer NOT NULL default 0
- `source_ref` String NULL (filename); `block_index` Integer NULL; `uploaded_by` String NULL
- `created_at` / `updated_at`
- unique `(coalesce(company_id, nil), supplier_id, pi_number)` as index
  `uq_scm_proforma_invoice_identity` (declared on the model AND in the migration, per the
  supplier_inventory precedent - CI is create_all)

`scm.proforma_invoice_line`
- `id` uuid pk; `invoice_id` -> `scm.proforma_invoice.id` CASCADE NOT NULL
- `line_no` Integer NOT NULL; `row_number` Integer NULL (where in the file)
- `item_code` String(100) NOT NULL (verbatim); `description` Text NULL
- `qty` Numeric NOT NULL; `uom` String(20) NULL
- `unit_price` Numeric NULL; `amount` Numeric NULL
- `po_ref` String(100) NULL; `remark` Text NULL
- `product_id` -> `products.id` SET NULL, NULL (exact code match only)
- `created_at`
- index on `invoice_id`, index on `po_ref`

Migration `374_scm_proforma_invoice`: `down_revision = ("373_merge_372_flyer_specs",
"373_merge_media_into_main")` - main currently carries two heads, so this revision joins
them and adds its tables in one step. Re-check `alembic heads` after the pre-push rebase; if
somebody merged the heads first, point at that merge instead. The migration also:
- seeds the `proforma_invoice` aliases (module-level `_ALIASES` + `seed(bind)`, replayed
  from `scripts/bootstrap_env.py` alongside 338/357/358);
- declares `company_id` with its `companies` FK and index (what `CompanyScopedMixin` +
  `create_all` produce), so a migrated database and a CI one are the same shape;
- registers `scm.proforma_invoice.upload` and sweeps it onto holders of `scm.reorder.run`,
  excluding `integration\_%` roles (pattern: 361_spec_registry_grant_sweep). The registry
  entry is ALSO added to `app/rbac/permission_registry.py` so a fresh database has it.

### Aliases (`doc_type = proforma_invoice`)

| field | aliases |
| --- | --- |
| item_code | `产品型号`, `编号`, `型号`, `ITEM CODE`, `MODEL`, `Item No` |
| description | `品名`, `DESCRIPTION`, `Description`, `货名` |
| spec | `规格` |
| qty | `数量`, `产品数量`, `QTY`, `Quantity` |
| uom | `单位`, `UOM`, `Unit` |
| unit_price | `RMB`, `单价(元)`, `单价`, `UNIT PRICE`, `Unit Price`, `PRICE` |
| amount | `金额（rmb）`, `金额`, `总价（元）`, `总价`, `AMOUNT`, `Amount`, `TOTAL` |
| po_ref | `其他`, `PO NO`, `PO No.`, `PO`, `订单号`, `客户订单号`, `Order No` |
| remark | `备注`, `REMARK`, `Remarks` |
| brand | `商标` |
| cartons | `箱数` |
| pi_number | `货单号`, `发票号`, `PI NO`, `Invoice No`, `Proforma No`, `PI No.` |
| invoice_date | `日期`, `Date`, `Date 日期`, `Invoice Date` |
| container_no | `货柜号`, `Container No`, `Container No 货柜号` |
| bl_no | `提单号`, `B/L NO`, `BL No` |
| currency | `币种`, `Currency`, `CURRENCY` |

`normalize_header` strips punctuation and spaces, so `Date 日期：` -> `date日期` and the
combined-label spellings are listed so the labelled-cell scanner resolves them whole.

## Reader - `app/services/scm/proforma_invoice_reader.py`

Refactor `packing_list_reader` minimally so its block machinery is reusable:
- `_labelled(raw, resolver, fields=_BLOCK_FIELDS)` takes the block-field tuple; a candidate
  value that is itself a LABEL is not a value, and ends the search for that field - stops
  the `bl_no='Date 日期：'` defect (AC-P2.4) for both channels. A cell is a label three ways
  (`_is_label`): it resolves to a known field, it ends in a colon, or it is the one-cell
  `label：value` form whose head resolves. The last two are what correct the PACKING-LIST
  channel, where `Date 日期：` resolves to nothing under its own doc type and `货柜号：XXXU1`
  resolves to nothing as a whole cell - a resolve-only test would have fixed the proforma
  channel and left the other one reading a label as a bill of lading.
- `_is_header(mapped, required=("item_code","qty"))` parametrised.
- `_line_from` stays packing-list specific; the proforma reader has its own `_pi_line_from`.
- The currency hint is one helper for both readers, `currency_resolution.price_column_currency`
  (over `currency_from_text`), so the two channels cannot disagree about what money one file
  is in.

`read_workbook(data, resolver=None, *, db=None) -> ProformaReadResult` with
`documents: list[ProformaDocument]`, each `{index, pi_number, invoice_date, container_no,
bl_no, currency_hint, header_row, stated_total, lines: list[ProformaLine]}`. Header requires
`item_code` + `qty` + `unit_price` mapped on one row (AC-P2.6). Block fields:
`pi_number, invoice_date, container_no, bl_no, currency`. A totals row (`合 计`, `总金额`) has
no item code -> not a line. Blank numbered rows (`序号` only) -> not a line.

The document NUMBER is not derived here: a derived one is positional and needs the file's
own name, which `read_workbook` does not have. The reader returns what the document states
(else `None`) and `proforma_invoice_service.pi_number_for(doc, source_ref=)` derives
`PI-<stem>-<index>`, mirroring `packing_list_service.shipment_number_for`.

Currency hint: from the RAW header text of the unit_price / amount columns and a labelled
`currency` cell, via a tiny ordered map (`rmb|元|cny|¥` -> CNY, `usd|us$` -> USD,
`myr|rm` -> MYR; check `rmb` before `rm`). Exposed as `currency_hint` on the document,
never applied silently - the service resolves it.

Date parsing: datetime cell; `dd.mm.yyyy`; `yyyy-mm-dd`; `yyyy.mm.dd`; `yyyy/mm/dd`. Anything
else -> None + a RowProblem naming the row.

## Currency resolution - `app/services/scm/currency_resolution.py` (small, shared)

`resolve_currency(db, *, supplier_id, requested, stated) -> (code|None, source)` where
source in `form | document | supplier_price_list | none`. Supplier price list = distinct
non-null `product_suppliers.currency` for that supplier (company-scoped session), exactly one
value -> that value. Used by both the proforma service and `packing_list_service.apply`.

## Service - `app/services/scm/proforma_invoice_service.py`

`preview / validate / apply`, same three-function shape as `packing_list_service`.
- `_summarise` per document: `pi_number, invoice_date, container_no, lines, qty, total,
  stated_total, unmatched_items, currency, currency_source`.
- `validate`: errors = unreadable / missing columns / no document / priced-lines-without-
  currency; warnings = unmatched codes, ignored headers, stated total != line sum.
- `apply(db, data, *, supplier_id, currency=None, source_ref, actor)`: 422 when unreadable
  or currency unresolved for priced lines; upsert header by identity, delete + reinsert
  lines; returns `{documents_created, documents_updated, results[...]}` + summary.
- `serialize(inv, with_lines)` for the GET routes (supplier code/name, product code).

## Route - `app/api/v1/scm/proforma_invoices.py`, mounted in `app/api/v1/scm/__init__.py`

`/proforma-invoices/preview` POST, `/proforma-invoices/apply` POST (`validate_only`),
`/proforma-invoices` GET (supplier_id, limit), `/proforma-invoices/{id}` GET,
`/proforma-invoices/{id}` DELETE. Form fields: `supplier_id` (required), `currency`
(optional). `_UPLOAD = require_permission("scm.proforma_invoice.upload")`,
`_READ = require_permission("scm.dashboard.view")`. Uses `read_upload`.

## G3c - `packing_list_service.apply`

Add `currency: Optional[str] = None` kwarg (route exposes it as a Form field). Resolve via
`resolve_currency` with `stated = reader currency hint` (the packing-list reader gains the
same `currency_hint` on its result, from the same helper). If any line has `unit_price` and
no currency resolves -> `AppException(422, "state the currency ...")`; `validate` reports the
same as an error. Each `InboundShipmentLineCreate` gets `unit_cost=ln.unit_price` and
`currency=<resolved>` (both None when the line has no price). Everything else in `apply`
untouched (another worker owns the container-replace behaviour and `supplier_id` on lines).

## Tests (Postgres only)

- `tests/scm/test_proforma_invoice_reader.py`: builds the two real shapes cell-for-cell with
  openpyxl (fixture builders `preloading_list_workbook()` and `kailu_proforma_workbook()` in
  `tests/scm/fixtures/proforma_shapes.py`, bank rows replaced by placeholder text) and asserts
  AC-P2.2 .. P2.6 numbers exactly (5 docs / 30 lines; 1 doc / 19 lines / 3 po_refs; the
  newline code; dates; CNY hint). Plus a seeded-alias check against the migration's
  `_ALIASES` like `test_the_seeded_aliases_are_the_ones_this_suite_assumes`.
- Optional real-file test: skipped unless `SCM_PROFORMA_SAMPLES_DIR` points at a directory
  holding the two originals (they are not committed - Kailu's carries bank details).
- `tests/scm/test_proforma_invoice_import.py`: `pg_session` World (supplier, products);
  apply both shapes; idempotent re-upload; unmatched codes named; currency order (form >
  document > price list > error); 422 without currency; product exact-match only.
- `tests/scm/test_proforma_invoice_routes.py`: 403 without permission, preview / test /
  apply / list / detail / delete happy paths, validation error on bad supplier.
- `tests/scm/test_packing_list_import.py`: add "the shipment line carries the unit price
  and currency the file stated", "priced list without currency is refused", "unpriced list
  is unaffected", "the label after a blank BL is not read as the BL".
- `tests/test_s3b_cost_variance_edges.py` or the import test: a stated CNY survives an
  allocation against a MYR PO line.

## Deviations from the pipeline, stated

- No Phase 1 FE mock: the slice has no screen (the consuming screen is the next task). The
  channel is verified by pytest against real-shape fixtures and by an evidence run with
  curl against the running backend, not by agent-browser.
- Grill / lavish review steps need a human in the loop; this ran unattended under a
  firstmate brief, so decisions taken are recorded here (currency order, positional PI
  number, product exact match, both price homes) for the reviewer to challenge.
- Coder runs in this disposable worktree rather than a nested one: the whole worktree is
  the isolation.

## DoD gate

1. Mock -> real: n/a (no FE).
2. Existing rows: none to backfill (new tables; shipment-line prices only from now on).
3. New permission -> grant sweep in the migration (AC-P4.3).
4. New DB column reaches the FE: n/a this slice; recorded for the verification task.
5. User-perspective verification: API evidence run recorded in the PR body.
