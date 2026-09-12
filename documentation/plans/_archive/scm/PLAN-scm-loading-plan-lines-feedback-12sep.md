# PLAN - Loading plan Lines tab feedback, 12 Sep 2026

**Status:** MERGED 12 Sep 2026 in PR #849 (jayson-odoo/sorento-crm). Lane `fix/loading-plan-lines-feedback-12sep`. UAC: `scm-loading-plan-lines-feedback-12sep-acceptance-criteria.md`.

## Journey

Ms Tee opens a loading plan (Supply Chain > Loading Plan > a plan), lands on the Lines tab, and reads one table: what to ask this supplier for. She expects (1) the rows to be what the supplier's file names, or what we buy from them when there is no file; (2) each row to show its code once, not twice; (3) SPO and Incoming PL never to count the same container twice; (4) to find one product in a 60-row table by typing its code.

Four items, one lane, one PR. Item 1 is the universe rule below; items 2-4 are in the UAC as AC-N1..N3.

## Why (item 1, the universe)

The captain looked at the Lines tab of a loading plan with a stock list attached and asked what
the product list was based on. The answer was "three things unioned" (`product_suppliers` links,
the plan's statement, every non-dismissed supplier code alias plus the drivers of aliased sets -
AC-E0 / AC-D3 in `scm-loading-plan-feedback-2sep-acceptance-criteria.md`). The alias leg in
particular was "too confusing" - the captain's words - and a plan with a file on it was showing
products the file never named.

## The rule (supersedes AC-E0 and AC-D3)

| Plan has a statement (stock rows or invoice lines on file, matched or not) | Universe |
| --- | --- |
| Yes | The products and sets the statement's rows are bound to. Nothing else. |
| No ("No file" plan, or a legacy pre-454 plan with nothing on file for the supplier) | `product_suppliers` links only. |

Aliases keep their job of BINDING a file's code to our product or set (rung 0 of the matcher,
the Supplier codes tab). They are no longer a membership leg of their own: an aliased product
that the current file does not name is not a row, and neither is one on a no-file plan.

Consequences, stated so nobody is surprised:

- File-mode: a linked product with open SO need that is NOT on the file disappears from the
  ask. The file is the ask.
- File-mode, all rows unmatched: zero rows until codes are matched on the Supplier codes tab.
- No-file mode: no holdings exist, so every row is a demand row; there are no folded
  "held with no open demand" rows.
- Placement is unchanged: a candidate with open demand is ranked, a candidate the file says
  is held (packed or unfinished > 0) with no demand is a folded row, a candidate with neither
  is dropped. Netting, ranking, sets (driver reads), horizon: untouched.

## Change

- `container_request_service._statement` also answers "is anything on file" (`on_file`).
- `build`: `universe = holdings | drivers` when `on_file`, else `_linked_products` - which
  shrinks to the `product_suppliers` query alone.
- Tests pinning AC-E0 / AC-D3 rewritten; new tests in `tests/scm/test_container_request_universe_file_or_links.py`.
- FE comment at `ContainerRequestSection.tsx` (AC-A1 note) updated; no FE behaviour change.

## Items 2-4 (captain, same session)

- **Product cell shows the code twice.** `product_name` equals `item_code` for most of this
  supplier's rows, so the subtitle repeats the title. The same fix already exists on the
  order-inquiry worklist (`orderInquiryWorklistColumns.tsx:316`: subtitle only when
  `product_name !== item_code`). Set rows keep their "Figures from <driver>" subtitle.
- **SPO and Incoming PL double-count.** Row 1 shows SPO 10,000 and Incoming PL 10,000 for
  the SAME container: the packing list already has its SPO. The netting formula already
  subtracts only `incoming_pl_unallocated` (R6), but the CELL, the Total supply column and
  the Incoming PL lightbox still show the gross figure. Rule: Incoming PL = the part of a
  packing list not yet on an SPO (`PL_UNALLOCATED_SQL`), everywhere it is shown. A shipment
  fully on an SPO is not listed in the lightbox. `incoming_pl` on the payload becomes that
  figure (and `incoming_pl_unallocated` stays, equal to it, so the formula tooltip and any
  reader of either key keep working). Total supply = on hand + SPO + Incoming PL, which
  now foots.
- **Search the Lines table by product.** Client-side filter (the rows are already all on
  the client; no server round trip is needed) on `item_code`, `product_name`, `set_code`,
  case-insensitive substring, via the shared `ListSearchInput`, in the toolbar row beside the
  Table / Schedule toggle. Filters both the ranked table and the folded rows; the stat cards
  and Save (N) are not affected by the filter. Schedule view: the same filter applies to its
  rows.
