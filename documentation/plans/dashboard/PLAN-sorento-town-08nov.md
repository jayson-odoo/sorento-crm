# PLAN: Sorento Town (2.5D daily overview, cached snapshot)

Status: mock v3 APPROVED (owner 8 Nov 15:51, "keep the solution simple and straightforward"). Phase 0 built and reviewed; Phase 0 extension (compare, deliveries) + Phase 1 screen in progress, tester-first. Track: L.

Lane: SORENTO-TOWN. Owner go: 8 Nov 2026 ~13:35 MYT. Research: crew report of 8 Nov (embedded in the lane brief).

## Hard rule

The town never runs a DB query per viewer. One leader-only scheduler job builds one gzip JSON
snapshot per company; `GET /api/v1/town/snapshot` reads Redis only. A test asserts the endpoint
makes no DB call.

## Order of work

1. Behaviour card (this file, section "Behaviour card") answered by the owner. **Blocks everything.**
2. Lavish static mock (one real company day from dev data) with an element -> component map.
   Build of the town screen starts only after the owner OKs the mock.
3. Phase 0 (snapshot backend) may start in parallel with step 2 once the card is answered.
4. Phase 1 MVP screen; Phase 2 life + team-first gamification.

## Behaviour card (owner decisions, each with a recommendation)

| # | Decision | Options | Recommendation |
|---|---|---|---|
| 1 | Who sees RM amounts | (a) holders of `sales.reports.view` (+ superadmin/admin); others see counts only. (b) everyone with town access. (c) admin only | (a): the town total equals the sales report, so it inherits the sales report's permission (`sales.reports.view`, already used by 10 endpoints). Redaction happens server-side when the cached snapshot is served (two cached variants per company: full and redacted), never in the browser. |
| 2 | Which dealers get shops | (a) top 30 by 90-day invoiced sales (one sales calc), refreshed nightly; anyone invoiced today also gets a stall for the day. (b) every active dealer. (c) per-agent: my dealers | (a): ~30-50 buildings fits the <100 draw call budget; (b) is hundreds of buildings and no glance value. |
| 3 | What the "Approvals" sign counts | (a) purchase requests `approval_status = pending` (`PurchaseRequestHeader`, `models/procurement.py:1187`). (b) + project quotation documents awaiting approval (`models/projects.py:1245`). (c) + dealer-kit editions `pending_approval`/`resubmitted` (`models/dealer_kit.py:643`). (d) form SLA overdue | (a)+(b) for phase 1, shown as one number with a per-kind breakdown on click; form SLA overdue renders as "fires", not approvals, so it is not double counted. |
| 4 | May an office wallboard show customer names | (a) no: wallboard mode shows shop rank numbers and the total only. (b) yes | (a): a wallboard is a public screen (visitors, dealers' staff in the showroom). Names stay on the signed-in personal view. |
| 5 | Which reorder field drives the "!" | (a) `scm.ReorderLevel.level` (`models/scm.py:109`), buyer-owned, per product with optional per-location override; NULL = not set, no "!". (b) `Stock.reorder_point` (`models/inventory.py:134`). (c) `Product.reorder_level` (`models/product.py:346`) | (a): it is the field the SCM reorder engine plans against and only a person sets it, so a "!" means the same thing as a reorder suggestion. (b)/(c) are older mirrors; showing a "!" the buyer does not act on trains people to ignore it. |

### What dev data changed (8 Nov, crew data request; structural facts only, no real names or amounts on GitHub)

The real figures (one full day, top dealers, examples) live with the owner via crew, not in the repo.

- **Decision 2:** the 90-day all-types top 30 is roughly half project accounts plus related-company
  accounts; the Dealer sales type (`invoiced_sales.sales_type()`) excludes both. Sales are keyed per
  AutoCount debtor account, and one dealer company can hold several accounts (`[A/C I]`, `[A/C III]`),
  which reorders the top 30 when merged. Revised recommendation: **2a = top 30 Dealer-type customers by
  90-day invoiced sales, one shop per AutoCount account** (labelled with its account suffix), because
  that is exactly how the Invoiced report groups and the town total must match it; a project-sales
  "site" district and per-company merging are phase 2 options, not phase 1. The day banner still shows
  the all-types total (equals the sales report).
- **Decision 3:** every approval queue is near empty on a normal day (PR pending: 1; project quotation
  documents pending: 0; dealer-kit editions: 0). Recommendation unchanged ((a)+(b) one number), and the
  sign shows "All clear" at zero rather than disappearing. Note: `purchase_requests` has no company
  column, so the PR count is cross-company until that is fixed (snapshot shows it on every company's
  town; flagged for the owner).
- **Decision 5:** (b) `stock.reorder_point` is set on 0 of ~60k stock rows: drop it. (a) and (c) are set
  on ~11.3k products and equal on every product that has both (sourced from AutoCount). (a) has no
  per-location level rows, so a level is product-wide: "below" = product availability summed across
  warehouses. ~1.75k products sit below level, far too many to mark one by one. Revised recommendation:
  **5a, with the "!" on the warehouse district as a count ("1,7xx below reorder"), click -> the existing
  SCM reorder list; per-warehouse stock bars show volume, not "!"**, because a product-wide level cannot
  say which warehouse is short.
- **Warehouses:** 67 active SRT warehouses, most are sub-locations of a few pools (BRW, MWH, DC1, WH3,
  RSW, HQ ...). Recommendation: **one building per pool** (sub-locations folded in), so ~6-8 warehouse
  buildings, not 67.

## Owner answers (8 Nov ~13:55 MYT: "All follow your rec")

1a amounts for `sales.reports.view` holders + superadmin/admin, server-side redaction, a full and a
redacted snapshot per company. 2a top 30 Dealer-type customers by 90-day invoiced sales, one shop per
AutoCount account labelled with its [A/C] suffix, plus a day stall for any Dealer-type customer invoiced
today. 3a approvals = pending PRs + quotation documents awaiting approval, one number with a per-kind
breakdown, "All clear" at 0, PR count on every company's town. 4a wallboard shows no customer names.
5a one "!" with a count on the warehouse district -> existing SCM reorder list; per-warehouse bars show
volume. 6a one building per warehouse pool, sub-locations folded in.

Decision taken without an ask (simplest thing): the town itself needs only a signed-in staff session (no
new permission slug). Without `sales.reports.view` a viewer sees no amounts and no dealer identity or
ranking (crew ruling 8 Nov, security review S1). No module guard: the route mirrors no single module.

## Phase 0 contract (snapshot backend)

### Honest scope of "no DB call per viewer"

Staff tokens are opaque sessions resolved on every request (`get_current_user`, `app/dependencies.py`)
and the company scope resolver reads the session too (`company_scope_resolver.py:478`). Those auth
lookups are paid by every endpoint and stay. The guarantee is: **the town route reads NO business table**
(no billing, customer, stock, warehouse, reorder, PR or quotation row); the snapshot comes from Redis
only. The no-DB test records every SQL statement during the request and fails on any statement outside
the auth allowlist (sessions, users, roles, permissions, company grants).

### Service: `app/services/town/snapshot.py`

- `build_snapshot(db, company_id: str, day: date, *, now: datetime) -> dict` - the FULL variant.
- `redact(snapshot: dict) -> dict` - a deep copy with every amount key removed (`today.amount`,
  `shops[].today_amount`, `shops[].ninety_day_amount`) AND dealer identity removed (`name`, `code`,
  `rank`; `key` becomes an opaque per-snapshot index): crew ruling 8 Nov on security review S1, mirroring
  `leaderboard_service.py:28` (the per-customer ranking needs `sales.reports.view`). Counts stay.
- `strip_names(snapshot: dict) -> dict` - wallboard: `shops[].name`, `code`, `today_amount`,
  `ninety_day_amount` removed and `key` made opaque (decision 4a: rank numbers and the total only).
- 90-day ranking cached once per company per MYT day in `town:{company}:{day}:ranking` (owner 2a
  "refreshed nightly"), computed on the first build of each day (about 07:00) inside a savepoint of the build's own session
  with a 30 s statement timeout, back to 5 s afterwards; on failure an empty ranking is cached for 30
  minutes (stalls only) instead of retrying every tick. The 3-minute build computes only today's
  figures (review rounds 1 and 2).
- `store(redis, company_id, day, full: dict) -> str` - writes gzip JSON under
  `town:{company_id}:{day}:full` and `town:{company_id}:{day}:redacted` plus
  `town:{company_id}:{day}:version` (sha1 hex of the full JSON, sorted keys); TTL 36 h; returns version.
- `load(redis, company_id, day, variant) -> tuple[bytes, str] | None` - (gzip bytes, version).
- `run_town_snapshot_tick(now=None)` - the scheduler job: does nothing outside 07:00-22:05 MYT; takes
  a Redis lock `town:lock` (SET NX EX 240) and returns if held; for each active company: build on a
  session from the read replica when `TOWN_REPLICA_DATABASE_URL` is set (else primary) with
  `SET LOCAL statement_timeout = 5000`, then store; a failure of one company is logged and the next
  company still runs. The first tick at or after 22:00 MYT also upserts the `town_days` row.
- Registered leader-only in `start_scheduler` (`app/scheduler/task_scheduler.py:851`) as an
  `IntervalTrigger(minutes=3)` job.

### Snapshot JSON (full variant), schema version 1

```json
{
  "schema": 1, "company_id": "...", "day": "2026-11-03",
  "as_of": "2026-11-03T15:42:00+08:00", "data_as_of": "<max billing_documents.last_synced_at, ISO or null>",
  "phase": "day | night",                       // night when as_of >= 22:00 MYT
  "today": {"amount": "512345.60", "invoice_count": 237, "credit_note_count": 1, "customer_count": 110},
  "shops": [
    {"key": "<customer_id>", "code": "300-X001", "name": "EXAMPLE TILES SDN BHD [A/C III]",
     "account_label": "A/C III", "kind": "shop", "rank": 1,
     "ninety_day_amount": "123456.78", "today_amount": "20111.40", "today_docs": 3}
    // kind "stall": Dealer-type customer invoiced today, outside the top 30; rank null
  ],
  "warehouses": [{"pool": "WH01", "on_hand": 800000, "available": 900000, "locations": 24}],
  "reorder": {"below_count": 1749, "set_count": 11307},
  "approvals": {"total": 1, "purchase_requests": 1, "quotation_documents": 0}
}
```

Rules, each a test:
- `today.amount` is the SUM of `invoiced_sales.signed_amount()` over `posted()` documents of the company
  with `doc_date = day` (all sales types). It equals the line figure (`signed_line_amount()` over
  `counted_line()`), so a document with a subtotal line is not double counted. Amounts are decimal
  strings with 2 places.
- `invoice_count` counts posted IV + CS (+ DN) documents; `credit_note_count` counts CN; `customer_count`
  distinct `customer_id`.
- Shops: top 30 by `signed_amount()` over the 90 days ending on `day` (day-89 .. day) among documents
  whose `sales_type()` is `dealer`, grouped by `customer_id` (= one AutoCount account); ties by code.
  `account_label` is the `[A/C ...]` suffix parsed from the name, else null. Stalls: Dealer-type
  customers with a posted document today not in the top 30. Name = `coalesce(customers.customer_name,
  billing_documents.customer_name)` as the Invoiced report shows it.
- Warehouses: active warehouses of the company folded onto their pool (`pool_warehouse_id`, else
  itself); `on_hand` / `available` = sums of `stock.quantity_on_hand` / `quantity_available`.
- Reorder: `scm.reorder_level` rows of the company with `warehouse_id IS NULL`, product `is_active` (the table has no active flag, `scm.py:109-145`), `level > 0`
  (`set_count`); `below_count` = those whose product's summed `quantity_available` over warehouses with
  `is_active AND counts_as_available` is below `level` (no stock row = 0).
- Approvals: `purchase_requests.approval_status = 'pending'` and not voided (no company column: same
  count on every town); quotation documents of the company whose approval status key is
  `pending_approval` or `resubmitted` (`project_quotation_approval_service.py:60-62`).

### Table `town_days` (migration)

`id uuid pk, company_id uuid not null, day date not null, snapshot jsonb not null, events jsonb not null,
created_at, updated_at`, unique (company_id, day). `events` = the day's posted documents in creation
order: `[{"at": "HH:MM" (MYT, from `billing_documents.created_at`), "shop_key": "<customer_id or null if not a shop>", "kind": "invoice|credit_note",
"amount": "..." (signed: negative on a credit note)}]` (replay, phase 2). `warehouses[].locations` counts the pool itself plus its active sub-locations. `shops[].key` stays on the wallboard variant: it is a click key, never rendered. Company scoped (`CompanyScopedMixin`).

### Endpoint `GET /api/v1/town/snapshot?mode=wallboard`

- Signed-in staff user (`get_current_user`); variant = full if the user holds `sales.reports.view` or is
  superadmin/admin, else redacted; `mode=wallboard` additionally strips names, codes, per-shop amounts and
  customer ids (from the cached bytes, no DB).
- Today's MYT date, the user's active company. Redis only. No snapshot yet -> 200 `{"pending": true}`.
- `ETag: "<version>-<variant>[-wb]"`; `If-None-Match` equal -> 304, empty body.
- Body served as the stored gzip bytes with `Content-Encoding: gzip`, `Content-Type: application/json`,
  `Cache-Control: private, no-cache`.
- Rate limit 30 requests/minute per user (Redis INCR `town:rl:{user_id}:{epoch_minute}`, EX 120) -> 429.
- Router mounted in `app/api/v1/__init__.py`.

## Phase 0 sketch (superseded by the contract above)

- `app/services/town/snapshot.py`: build(company_id, day) -> dict, reads via optional replica URL (5 s statement timeout, fall back to primary), sales via `services/sales/invoiced_sales.py`.
- Leader-only APScheduler job in `app/scheduler/task_scheduler.py`, every 3 min 07:00-22:00 MYT, skip if a run is in flight.
- Redis `town:{company}:{date}:{full|redacted}` gzip JSON + version; end-of-day `town_day` row (snapshot + event log).
- `GET /api/v1/town/snapshot`: Redis only, ETag/304, ~30/min per user.
- Tests (red first): town total == sales report for the day; endpoint makes no DB call; redacted variant has no amount keys; rate limit.


## Mock v3 approved (owner 8 Nov 15:51): the screen answers five questions

"Ok, keep the solution simple and straightforward." Build exactly v3
(`documentation/plans/dashboard/mock/sorento-town-mock.html`), nothing more. Gamification is a later phase.

1. How much did we sell today? Scoreboard: RM (full variant only), invoices, change vs same weekday last week.
2. Who bought today? Only shops with `today_docs` lit, with a tag; the rest grey; "+N more dealers bought today".
3. What stock is low? One red "! N low" bubble on the warehouse district.
4. What must go out? Lorries at the depot, "To deliver: N" (lorries drawn capped at 10).
5. What needs a decision? Approvals office with a badge.
Always-on legend, a "Tap any building" hint on first open, and the 2D cards beside the 3D view
(the same five answers; they are the only view without WebGL or with reduced motion).

### Phase 0 extension (snapshot schema 1 gains two keys)

- `compare`: `{"label": "Tue 27 Oct", "last_week_amount": "...", "last_week_invoice_count": n}` for
  `day - 7` up to the same time of day (documents with `created_at <= as_of - 7 days`; the whole day once
  the phase is night, from 22:00 MYT; owner answer (a), 8 Nov; `created_at` is when the CRM ingested the document, so a document ingested late drops out of
  the daytime figure), same `invoiced_sales` expressions as `today` (posted, signed amount, company). Amount
  removed by `redact()` and kept by the wallboard only for a full viewer (as `today.amount`).
- `today.dealer_customer_count`: distinct `customer_id` of today's Dealer-type documents (feeds the
  "+N more dealers" sign: N = dealer_customer_count minus lit shops).
- `deliveries`: `{"to_deliver": n}` = distinct sales orders of the company with at least one line
  where `line_status = 'open'`, `qty_ordered - qty_delivered > 0`, and
  `coalesce(line.required_date, header.requested_delivery_date) <= day` (due today or overdue).
  Definition (a) from the v3 ask; the owner's "keep it simple" approval did not pick another, so the
  recommendation stands. A count only: no amount, no names, same in every variant.

### Phase 1 screen (frontend)

- Route `/town` under `app/(protected)/town/`, its own page; the three.js scene loads through
  `next/dynamic` with `ssr: false` so no other page downloads it. Menu entry for every signed-in staff
  user (no permission), in the existing menu config.
- Layering per CLAUDE.md: `services/townService.ts` (`getSnapshot()` via `lib/api-client`, sends
  `If-None-Match`, a 304 keeps the last snapshot) -> `hooks/useTownSnapshot.ts` (polls every 60 s only
  while `document.visibilityState === 'visible'`) -> components.
- Components: `TownPage` (PageHeader "Town" + as-of chip + the one CTA "Wallboard" toggling
  `mode=wallboard`), `TownCards` (the five 2D cards), `TownScene` (three.js, orthographic, InstancedMesh,
  render on demand, 30 fps cap while dragging, pixel ratio <= 1.5, no shadows, pauses on a hidden tab),
  `TownPanel` (the side panel a tap opens; links go to the existing screens), legend + hint in TownScene.
- WebGL missing or `prefers-reduced-motion: reduce` -> cards only. `{"pending": true}` -> an empty state
  (heading + hint, no button). Amount fields absent -> show counts only, never "RM 0".
- Tap targets reuse existing permission-checked screens: sales report, the customer's invoices, the SCM
  reorder list, the outstanding sales orders / deliveries screen, purchase requests / quotation approvals.
- Usable at 375 px and 1280 px. No UUIDs rendered. Hint dismissed on first tap or after 6 s, remembered
  in localStorage (wrapped in try/catch).
