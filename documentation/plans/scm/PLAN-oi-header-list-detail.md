# PLAN - Order inquiries: header list (All / Outstanding / Completed) + OI detail page, monthly OI number, fixed raised date with raise history

Status: Phase 1 mock signed off by owner 21 Sep 2026 (hands-on, :3080); Phase 2 building, tester first
UAC: `oi-header-list-detail-acceptance-criteria.md` (the journey is its first section)
Branch: `feat/oi-header-list-detail` from `origin/main`
Track: full `/feature` lane (migration + new routes + two screens)

## Owner rulings (21 Sep 2026)

- R1 The line worklist stays as a second view (`Documents | Lines`); the header list is default.
- R2 Completed = every non-cancelled line confirmed. A later change pulls the OI back to
  Outstanding.
- R3 Number is `OI-YYMM-NNNN`, month of the first raise, fixed for life; ALL existing headers
  are renumbered.
- R4 Confirm on the detail page acts on the ticked lines, else on the whole OI.
- R5 Raised date = first raise, fixed; every raise / reconfirm is traceable (who, when).
- R6 Link fixes (Choose document, Link, Unlink, Reject, Unconfirm) are available on the detail
  page in this lane.

- R7 (hands-on, 21 Sep) Product cell shows the code only; gear gains Auto link (ticked lines, else
  the whole OI); Link selected STAYS next to it; the outer switch key is `display=lines`.
- Lane stack: FE :3080, BE :8084, both from this worktree, DB `sorento_ai_automation_0918_1900`
  (owner handed it over, 21 Sep). pytest runs against that same DB through `tests/_pg_fixture.py`
  (every test rolls back), touched files only. Its `alembic_version` stamp is behind
  (`521_sales_report_month_fix`; the DB converges through `create_all`), so the lane's migration is
  applied there as idempotent DDL + its own backfill functions, never `alembic upgrade head`.
- Migration revision id: `523_oi_monthly_no_raises` (file `alembic/versions/523_oi_monthly_no_raises.py`),
  exposing `backfill_raises(bind)` and `renumber_inquiries(bind)` as module-level functions so the
  tests drive them on seeded rows (precedent: `tests/test_migration_454_order_inquiry_born_ack.py`).

## Measured facts (origin/main 170d6ece3 + 0921 prod copy, 21 Sep)

- The header already exists: `projects.order_inquiries` (`app/models/project_so.py:818-860`):
  `inquiry_no`, `project_sales_order_id`, `amendment_id`, `state`, `raised_by`, `raised_at`. No
  `created_at`. Rows hang off `order_inquiry_id`. The FE never lists headers; `inquiry_no` is a
  default-hidden worklist column.
- 0921 copy: 735 headers, all raised 8-21 Sep 2026, one company, 0 sales orders with two
  headers, 0 amendment headers (#992 holds), 31 headers with a line to confirm, 1 header with
  only cancelled rows, median 6 rows per header, max 242. 697 of 735 headers have no
  `so_supply_decisions` row (sheet migration), so decision revisions are NOT a usable raise
  history. `audit_logs` holds nothing for order inquiries (`__audit_track__` is off).
- `raised_at` / `raised_by` are re-stamped on every reconfirm
  (`project_order_inquiry_service.py:838-846`); 4 headers already sit more than a day after their
  earliest row.
- Number mint: `next_inquiry_no(bind, company_id)` + `before_insert` listener
  (`project_so.py:862-908`), MAX+1 on the flush's own connection, guarded by
  `uq_project_order_inquiry_no`. `NumberingService` (FOR UPDATE rule row) cannot run inside a
  flush listener (it queries through the Session).
- Confirm exists: `POST /order-inquiries/acknowledge`, `row_ids` or a `filter` payload
  (`api/v1/projects/order_inquiries.py:552`), permission `projects.order_inquiries.acknowledge`.
  #991 (confirm per SO) and #992 (one header per SO) are merged; their plan Status lines are stale.
- Worklist rows already resolve supplier, PO, SPO, location, instruction
  (`order_inquiry_worklist_service.py`), so the detail Lines tab needs one new filter, not a new
  serializer.
- No OI detail page exists; every OI link goes to the worklist filtered by SO number
  (`automation_triggers.py:441-460`, `SalesOrderDetail.tsx:1738-1765`).
- Reference pattern: PO / SPO allocations use a shared `ToggleGroup` for All / Outstanding /
  Completed (`SPOAllocationsList.tsx:457-472`). Prev/next is frontend only: `rowHref` +
  `buildDetailSearch` (`lib/listNavQuery.ts`), `useListPager`, `ListPager`, `DetailActions`.
  Detail tabs are `?tab=` with a per-page default. SO Lines footer totals are TanStack column
  `footer` functions. No shared "related documents" component exists; tabs are bespoke.
- GET `/order-inquiries/{...}` paths are crowded (`/summary`, `/export`, `/matrix`, `/po/{id}`,
  `/spo/{n}`, `/upload-jobs/{id}`), so header routes live under `/order-inquiry-headers` to avoid
  route shadowing (LESSONS: SLA route shadowing).

## Design (simplest thing that works)

No new permission, no new module, no registry. View = `projects.projects.view`, Confirm =
`projects.order_inquiries.acknowledge`, line actions = `projects.order_inquiry.action`, all
existing and already granted.

### S1 - monthly number + fixed raised date + raise history [BE, migration]

- `next_inquiry_no(bind, company_id, ref_date)`: prefix `OI-{yy}{mm}-` from `ref_date`
  (Asia/Kuala_Lumpur date of the raise), MAX within that prefix + 1, four digits. Same listener,
  same connection, same unique-constraint guard as today: the mechanism is kept because it is the
  one that works inside a flush, only the prefix and width change. `INQUIRY_NO_DIGITS = 4`.
  `inquiry_no` is `String(20)`, `OI-2609-0001` fits.
- Stop the re-stamp at `project_order_inquiry_service.py:838-846`: `raised_at` / `raised_by` are
  written once, at insert.
- New table `projects.order_inquiry_raises`: `id`, `company_id` (CompanyScopedMixin),
  `order_inquiry_id` FK CASCADE, `kind` (`raised` | `reconfirmed`), `raised_by` FK users SET
  NULL, `raised_at`. One writer: `ensure_inquiry` (insert = `raised`, reuse = `reconfirmed`),
  once per confirmation (guard: the same header is recorded once per service call; the import
  path's `_inquiry` records the same way). Why a table and not `audit_logs`: a history is a list
  so it needs rows either way; audit is off for this entity, carries no actor on batch paths,
  and cannot be backfilled cleanly, while this table takes the explicit `actor_user_id` the
  service already holds and a two-row backfill.
- Migration (one revision, id 32 chars or fewer, re-parented with `scripts/alembic-reparent.sh`):
  1. create the table;
  2. backfill per header: `raised` at `LEAST(raised_at, MIN(rows.created_at))`, `reconfirmed` at
     the old `raised_at` / `raised_by` when more than a minute later;
  3. set header `raised_at` to the first;
  4. keep the old number in a new nullable `legacy_inquiry_no` column (downgrade restores from
     it; search also matches it so a number quoted from an old email still finds its OI);
  5. renumber per company, per month, `ORDER BY raised_at, id`, in two passes (temp value first)
     so the unique constraint never trips.
- The shared local DB converges through `create_all`, so the lane applies the additive DDL
  idempotently on its own copy (backend CLAUDE.md).

### S2 - header list endpoint [BE]

`GET /api/v1/project-sales/order-inquiry-headers` in `app/api/v1/project-sales/order_inquiries.py`,
service `OrderInquiryHeaderService` in a new `app/services/order_inquiry_header_service.py`
(the worklist service is already 1.7k+ lines). One grouped query: header join project sales order
join core sales order / customer / project / agent / raised-by user, plus one aggregate subquery
over non-cancelled rows (`lines_total`, `lines_to_confirm`, `qty_total`). `query` also reaches inside the OI (owner markup 21 Sep): an `EXISTS` over the header's
non-cancelled rows on `item_code` / `stock_location`, next to the header-level matches (OI no,
legacy no, SO no, customer, project, agent), so a header is returned once. Status is derived, never
stored: `lines_to_confirm > 0` = outstanding. The header `state` column is left alone.

### S3 - detail, lines filter, related documents, whole-OI confirm [BE]

- `GET /order-inquiry-headers/{id}`: header + Order block + Customer block + counts + status +
  `raise_history`.
- `inquiry_id` filter added to the worklist list (`GET /order-inquiries`), to the acknowledge /
  unacknowledge `filter` payload, and to `POST /order-inquiries/auto-place` (gear > Auto link on
  the detail page, owner markup 21 Sep). Nothing else in those paths changes.
- `GET /order-inquiry-headers/{id}/related-documents`: two grouped queries over
  `order_inquiry_links` joined to PO lines / SPO allocations.
- `build_order_inquiry_link` takes the header id; the SO detail payload's `order_inquiries[]`
  entries gain `id`.

### S4 - Documents view [FE]

`app/(protected)/project-sales/order-inquiries/`: `page.tsx` renders a small view switch
(`?display=lines` = today's `OrderInquiriesClient`, untouched; default = new
`components/OrderInquiryHeadersList.tsx`). Copies `SPOAllocationsList` for the toggle + URL state
and `SalesOrdersGrid` for `rowHref` / `buildDetailSearch`. New hook `useOrderInquiryHeaders`, list
query key + `orderInquiryHeadersPagerQuery` in `_shared/hooks/useOrderInquiry.ts`, service
functions in `_shared/services/orderInquiryService.ts` (`buildDataGridParams`,
`extractApiError`).

### S5 - detail page [FE]

`order-inquiries/[id]/page.tsx` + `components/OrderInquiryDetail.tsx`, the `SalesOrderDetail`
shell: `PageHeader` + `BackToList`, header card, `DetailActions` (pager, gear, primary Confirm),
`Tabs` Lines / General / Related PO / Related SPO with `tab` defaulting to `lines`.
Lines tab reuses the worklist column cells (`orderInquiryWorklistColumns.tsx`: product, qty with
Was/Now, delivery date, supplier, PO, SPO, location, instruction, state pill) by exporting the
cell renderers, not by copying them. Gear actions reuse `useOrderInquiryHandshake`, the existing
Choose document / Reject dialogs and the deferred Unlink. Raise history uses `EventTimeline`.
Related PO and Related SPO are the shared `DataGrid` (owner markup 21 Sep), client-side over
the one related-documents response: sort, search, Columns, pagination, Qty linked footer total.
SO detail's "Order inquiries" field and per-line column link to the OI detail page.

### Not in this lane

- The per-project page (`project-sales/[projectId]/order-inquiries`) is untouched.
- No stat cards on the Documents view (they count lines; they stay on the Lines view).
- No header-level reject, no header export. Trigger to revisit: purchasing asks for it after use.
- MCP tool for OI headers: none exists for rows either; not added.

## Contract

```
GET /api/v1/project-sales/order-inquiry-headers
  ?state=outstanding|completed|all (default outstanding)
  &query= (OI no, legacy no, SO no, customer, project, agent, any line's product or location)
  &raised_by=<user id> &agent=<agent name> &project_id=<uuid>
  &sort=raised_at|inquiry_no|so_number|raised_by|lines_total|qty_total|customer|project|agent|so_date|status
  &dir=asc|desc (default raised_at asc) &page=1 &limit=25
-> { data: [Header], pagination: { total, page, limit } }   (`app/schemas/common.py::ListResponse`, the
   envelope every other list in this module already uses, the worklist included)

Header = {
  id, inquiry_no, legacy_inquiry_no,
  raised_at, raised_by_name,
  sales_order_id (core SO id, null when none), project_sales_order_id, so_number, so_date,
  customer_name, customer_code, project_id, project_title, agent_name,
  lines_total, lines_to_confirm, qty_total,
  status: "outstanding" | "completed"
}

GET /api/v1/project-sales/order-inquiry-headers/{id}
-> Header + { order_type, raise_history: [{ kind: "raised"|"reconfirmed", by_name, at }] }

GET /api/v1/project-sales/order-inquiry-headers/{id}/related-documents
-> { purchase_orders: [{ po_id, po_number, supplier_name, po_date, lines_linked, qty_linked }],
     spos: [{ spo_number, supplier_name, lines_linked, qty_linked }] }

GET  /api/v1/project-sales/order-inquiries?inquiry_id=<id>          (existing list, one new filter)
POST /api/v1/project-sales/order-inquiries/acknowledge   { filter: { inquiry_id } } | { row_ids }
POST /api/v1/project-sales/order-inquiries/unacknowledge { filter: { inquiry_id } } | { row_ids }
```

Every field is declared on the response model and asserted in a test (`response_model` drops
undeclared fields).

## Testing seams

- pytest on Postgres via `tests/_pg_fixture.py`, own seeded chain (company, project SO, header,
  rows, links); never `LIMIT 1` off existing data. Seams: `next_inquiry_no`, `ensure_inquiry`
  (raise history), `OrderInquiryHeaderService.list/get/related`, the `inquiry_id` filter, the
  acknowledge filter branch, the migration's renumber SQL (run against seeded legacy numbers).
- vitest: params builder, toggle mapping, Confirm label / disabled rules, status Badge mapping.
- agent-browser evidence run for AC-E2E-01, from the sidebar, 375px and 1280px.
- No full scm suite on the shared DB; touched files only, CI is the full gate.

## Slices

| id | scope | ACs |
| --- | --- | --- |
| P1 | Phase 1 FE against mocks: S4 + S5 | AC-HL-01..07, AC-DP-01..11 |
| S1 | number + raised date + raise history + migration | AC-NO-01..04, AC-RD-01..03 |
| S2 | header list endpoint | AC-LS-01..07 |
| S3 | detail, lines filter, related docs, confirm + auto-link filter, links | AC-DT-01..03, AC-CF-01..02, AC-AL-01, AC-LK-01 |
| W | swap mocks, vitest, browser evidence | AC-FE-01, AC-E2E-01 |

Security review applies (multi-company scoping on new routes + a new scoped table).
Docs: `guide-writer` updates the order inquiries user guide; `documentation/CONTEXT.md` Order
Inquiry entry gains "the OI document (header) carries the number purchasing quotes".

## Risks

- Renumbering changes numbers already quoted in sent emails. Mitigation: `legacy_inquiry_no`
  kept and searchable.
- MAX+1 under two concurrent first raises in one company can collide on the unique constraint
  (true today as well). One header per SO keeps contention low; the loser's confirmation fails
  cleanly and is retried by the user. Trigger to move to a locked counter: a collision seen in
  prod logs.
- Open PRs touching the same files (#1084 OI project label, #1078 bundle host, #1085 board):
  merge main into the lane before the PR, per the pre-PR gate.
