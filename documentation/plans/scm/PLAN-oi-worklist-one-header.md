# PLAN - Order inquiries: one header per SO, hide cancelled, Was/Now after a redirect, cascade skips used rows, raised-by per row

Status: planned (owner go 17 Sep 2026)
UAC: `oi-worklist-one-header-acceptance-criteria.md`
Branch: `feat/oi-worklist-one-header` from `origin/main`
Worktree: `../sorento_crm-oi-one-header`
Origin: SO314593 on prod, diagnosed 17 Sep 2026 (rev 1 10:11 by the batch apply, rev 2 11:25
"Reconfirmed by CS." after the network outage; 24 pcs of SPO-2026/09-0036 auto-linked onto
the released 182 row at 10:11:15; OI-000477 + OI-000734 on one order).

## Measured facts (origin/main, 17 Sep)

All paths are `sorento_crm_backend/` unless stated.

- `app/services/project_order_inquiry_service.py`
  - `auto_place_for_products` (about line 6206): the row query filters `state in (raised,
    partly_linked[, placed])`, `verb in _LINKABLE_VERBS`, `ack_state in linkable_ack`. No
    `redirected_to_pool` filter. `_redirect_row_if_received` (about 1331) leaves the released
    row `partly_linked` when its received link is short of its qty (182 vs 158), so the
    cascade reads the 24 as need. `link_now` goes through the same method.
  - `derive_for_book_change` (about 2355) mints a synthetic `SOAmendment`
    (`from_version_kind='planning_change_batch'`) and calls `_write`, which mints a NEW
    `OrderInquiry` with `amendment_id = amendment.id`. The docstring says this avoids the
    DB singleton on `amendment_id IS NULL` colliding with `confirm()` in the same apply.
    `ensure_inquiry` (about 2499) returns or mints the null-amendment header. Nothing reads
    `from_version_kind='planning_change_batch'` back for routing (grep: only the ESB
    envelope and the fulfilment_planning code string, unrelated).
  - `refresh_for_decision` (about 646): the fresh row is built at about line 946
    (`raised_row = OrderInquiryRow(...)`) with no `previous_qty` / `previous_delivery_date` /
    `note`. `_settle_row_in_place` (about 1130) returns False after
    `_redirect_row_if_received` returns True (about 1196), so the line falls through to the
    netting loop, where `redirected_to_pool` rows are skipped (about 888).
  - `_write` (about 2430) stamps `acknowledged_by = actor_user_id` on every derived row.
  - `project_order_inquiry_import_service.py` line 1480 stamps `acknowledged_by = self.actor`
    on every migrated row; line 1407 stamps the header `raised_by`.
- `app/services/order_inquiry_worklist_service.py`
  - `_RAISED_BY_ID = func.coalesce(SOSupplyDecision.confirmed_by, OrderInquiry.raised_by)`
    (line 445); `_RAISED_BY_NAME = User.name` joined on it; the `raised_by` filter (about
    847) and `raised_at` sort use the same expression. The header `raised_by` is re-stamped
    on every reconfirm (comment at 431).
  - `list(...)` takes `state: Optional[str]` (single value) and `kind`; `_NOT_OWED_STATES =
    (cancelled, actioned)` is applied only under `kind` (about 853). Facets return
    `by_state` over all rows.
- `sorento_crm_frontend/app/(protected)/project-sales/order-inquiries/components/`
  - `orderInquiryWorklistColumns.tsx` line 877: `accessorKey: 'inquiry_no'` column. The
    Qty cell already renders the (i) Was/Now off `previous_qty` (test at
    `orderInquiryWorklistColumns.test.tsx:529`).
  - `OrderInquiriesClient.tsx` line 576 builds params `{ ...filters, kind }`; the State
    filter sends `state=<value>`. Column preferences persist via the list-query column
    config (`listing_key`), so a default-hidden column is the DataGrid's initial
    `columnVisibility`, overridden by a saved preference.

## Design (simplest thing that works)

### S1 - cascade skips used rows [BE]

One filter added to the row query in `auto_place_for_products`:
`OrderInquiryRow.redirected_to_pool.is_(False)`. Same seam serves Confirm's raise pass,
Link now, Auto link all and the PO confirm. No other change. AC-OH-10..12.

### S2 - raised-by per row [BE]

`_RAISED_BY_ID = coalesce(SOSupplyDecision.confirmed_by, OrderInquiryRow.acknowledged_by,
OrderInquiry.raised_by)`. Every row born since G4 is born acknowledged by its raiser
(confirm, `_write`, importer), so the middle term is the row's own person. The join to
`User`, the `raised_by` filter and the facet keep using the one expression. Update the
comment at line 431. AC-OH-20..23.

### S3 - one header per SO [BE + migration]

`derive_for_book_change` stops minting the synthetic `SOAmendment`; it calls
`ensure_inquiry(order, actor_user_id=actor)` and writes its rows there. `_write` gains an
optional `inquiry` argument: when given, it does not mint a header and does not touch its
`raised_by`. `derive_for_amendment` (OCN) is unchanged. The collision the old docstring
feared does not exist: `ensure_inquiry` returns the row `confirm()` wrote earlier in the
same apply, and both writers append rows to it.

Handover email: `_hand_to_purchasing(order, inquiry, n)` runs as today, once, for the
reused header.

Data migration `oioh_0001_one_header_per_so` (Alembic, `< 32` chars): for every
`order_inquiries` row whose `so_amendments.from_version_kind = 'planning_change_batch'`,
find or mint the same order's `amendment_id IS NULL` header (copy `company_id`,
`project_sales_order_id`, `state`, `raised_by`, `raised_at` from the oldest moved header),
`UPDATE order_inquiry_rows SET order_inquiry_id = <target>`, delete the emptied header, then
delete the synthetic amendment. Row ids, links, claims, handover records untouched. Runs in
SQL, idempotent, downgrade is a documented no-op. Verified on `sorento_ai_automation_0915_1900`
before the PR (OI-000737 on SO314595 is the known case there). AC-OH-30..35.

### S4 - Was/Now on the fresh row after a redirect [BE]

`refresh_for_decision` collects, per line, the rows `_redirect_row_if_received` flipped IN
THIS CALL (a local list filled where the settle declines, about line 1196; the redirect
method returns the fragment it wrote, or the caller reads `row.note`). When it builds
`raised_row`, if that list is non-empty: `previous_qty` = sum of their `qty`,
`previous_delivery_date` = the first one's `delivery_date`, `note` = `Replaces <qty> used;
<document> received <date|in full> into <location>` joined with `; ` per released row. Rows
released in an earlier decision are not re-stamped. The existing FE (i) then shows it.
AC-OH-40..43.

### S5 - hide cancelled by default [BE]

In `list(...)` and the totals it feeds: when `state` is None, add
`OrderInquiryRow.state != INQUIRY_CANCELLED`. `state='cancelled'` still returns only
cancelled. Facets unchanged. Matrix, month strip and cards untouched. AC-OH-50..54.

### S6 - Order inquiry column hidden by default [FE]

`orderInquiryWorklistColumns.tsx` / `OrderInquiriesClient.tsx`: initial `columnVisibility`
marks `inquiry_no` hidden; a saved column preference wins. AC-OH-01. Phase 1 (no backend).

## No-motion list

Nothing animates. No new component, no new state.

## Testing seams

- S1: pytest on `auto_place_for_products` with a seeded product, one released row with a
  short received link, one fresh raised row, one open SPO allocation.
- S2: pytest on `OrderInquiryWorklistService.list` with a migrated row and a re-stamped
  header.
- S3: pytest on `planning_change_service.apply` (existing fixtures) asserting one header;
  migration test on a scratch DB with a synthetic `planning_change_batch` header.
- S4: pytest on `refresh_for_decision` through `ProjectSupplyService.confirm` with a
  received link.
- S5: pytest on `list` with and without `state`.
- S6: vitest on the columns module / client initial visibility.
- E2E: agent-browser evidence run on the lane stack (AC-OH-60..63).

## Slices and order

Phase 1: S6. Phase 2 (tester reds first, one coder): S1, S2, S5, S4, S3 (+ migration).
Phase 3: reviewer (Opus) with kill tests on AC-OH-10, AC-OH-21, AC-OH-40; browser
verification; guide-writer. No security-reviewer (no auth, ingest, upload or scoping change).

## Prod follow-up (owner, after deploy)

1. Migration moves OI-000734 and siblings onto their SO headers on `alembic upgrade head`.
2. SO314593 B2154-NL: on the used 182 row, chip `unlink` the 24 of SPO-2026/09-0036, then
   Actions > Auto link all so the live 220 row takes it.

## Backlog

- OCN amendment headers per amendment (trigger: a project-authored SO shows two headers).
- Drop the order inquiry number entirely (trigger: unused in emails/sheets for a month).
