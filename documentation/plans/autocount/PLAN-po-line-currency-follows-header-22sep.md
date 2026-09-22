# PLAN: a purchase-order line's currency follows its header, never an assumed CNY

Status: in progress. Track: small fix. Owner ruling 22 Sep 2026 ("we shouldn't assume CNY, let's go").
UAC: `po-line-currency-follows-header-22sep-acceptance-criteria.md`.

## Evidence (local 0921 prod copy, 22 Sep 2026)

- Chatbot `crm_procurement_po_last_cost_list` answered "CNY 31.83" for MAP4944A on
  PO-2020/09-0009; the PO detail page shows "RM 31.83". Neither is hardcoded: the MCP
  presenter prints `purchase_order_lines.currency`, the page prints
  `purchase_orders.currency`. Header = MYR (from AutoCount), line = CNY (our fill).
- AutoCount holds currency on the PO header only. The FoundryX push mirrors that: the
  header carries `currency`, every line's `currency` is absent. Both Sorento writers then
  fill the absent line currency with `DEFAULT_PO_CURRENCY = "CNY"` without reading the
  header:
  - `sorento_crm_backend/app/services/document_ingest_service.py` `_line_values` (~L1276-1279)
  - `sorento_crm_backend/app/services/scm/outstanding_import_service.py` `_refresh_money`
    (~L1893) and the new-line insert (~L2419-2423)
- Damage: 66,720 autocount lines whose currency differs from their header
  (MYR 20,358 / USD 46,317 / EUR 36 / SGD 9). Every one of them is line=CNY.
- The CNY default dates from the 28 Aug ruling for an AutoCount Excel export with NO
  currency column at all. That was a header-level fill; the line copy of it was wrong
  from the day a header currency became known.

## Change (one seam: "what currency does a PO line get when the row states none")

1. `document_ingest_service._line_values`: a line with no stated currency takes the
   HEADER's resolved currency (the value `_header_values` produced for this document,
   after its own fill). No CNY literal on the line path. If the header has none either,
   the line stays NULL.
2. `outstanding_import_service`: same rule in `_refresh_money` and the insert path - the
   fallback is `header.currency` (the `PurchaseOrder` row being written, already filled
   by the header rule at ~L2233-2236), never `DEFAULT_PO_CURRENCY` directly. A line that
   ALREADY holds a currency is left alone when the file states none (unchanged rule).
3. `spo_allocations` / shipping orders: untouched (per-row header-ish currency, not this
   seam). The HEADER CNY fill (`_header_values` ~L996, `outstanding_import_service`
   ~L2236) is untouched in this lane; flagged for a separate ruling in the PR.
4. Backfill: `sorento_crm_backend/scripts/backfill_po_line_currency_from_header.py`,
   `--dry-run` (default) / `--apply`; sets `purchase_order_lines.currency = purchase_orders.currency`
   where the header currency is set and differs from the line's, for `source_system = 'autocount'`
   lines; prints the per-pair counts before and after. Owner runs it on prod after deploy.
   No alembic migration (small fix track).

## Tests (red first, then green)

pytest only; touched files on `sorento_buc_ci` via `SORENTO_ENV_FILE=.env.ci-tests`.

- `tests/test_ingest_documents_v2_resolution.py`: rewrite AC-V1-9 to
  "header stated MYR, lines unstated -> every line MYR"; add "header stated USD, one line
  states CNY -> that line keeps CNY, the others USD"; keep "nothing stated anywhere ->
  header CNY (existing header rule), line CNY via the header, not via a line literal".
- `tests/scm/test_outstanding_import_po_columns.py` (or a new sibling): an upload whose
  rows state currency MYR -> header MYR AND line MYR (already true); an upload with a
  currency column on the header side only is impossible for a flat sheet, so the
  regression to pin is: existing line CNY, re-upload states MYR -> line becomes MYR
  (refresh), and a NEW line on a header already holding MYR with no currency column in the
  file -> MYR, not CNY.
- `tests/scm/test_backfill_po_line_currency.py`: seed 1 PO (MYR) with 2 lines (CNY, MYR)
  + 1 PO (CNY) with 1 line (CNY) + 1 non-autocount PO (MYR) line CNY; dry-run changes
  nothing and reports 1; apply flips exactly the one autocount CNY line to MYR.

## Not in scope

FE change: none (the page already prints the header currency). Chatbot presenter: none
(it prints the line's own currency, which is now right). Header CNY default: separate
ruling.
