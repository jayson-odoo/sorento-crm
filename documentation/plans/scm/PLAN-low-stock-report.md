# PLAN - Low stock report: a run-bounded Excel on the plan, and over WhatsApp

Status: in review - Phase 3 round 3 fixes landed, awaiting final console check + PR (14 Sep 2026). Round 3 (reviewer re-pass): a failed export after `pending` texts the contact, the prefix prune, one report read, the 502 no longer double-logged, the menu label, the wait-cap hint, the plan-timestamp title, docs re-synced. Round 2 (console round 3): MCP hop 10 s caps the sync wait, carried entities on a bare ask, rate limit 5 + busy reasons, empty-scope line. Round 1 (reviewer + security NOT READY): async to_thread, chat-route run guard + per-contact rate limit, company resolution from the contact, error never pending, row counts in one transaction, admission SQL company predicates, assistant bootstrap dropped.
UAC: `low-stock-report-acceptance-criteria.md` (same folder).
Domain: scm (with a chatbot/MCP half). Lane branch: `feat/low-stock-report`. One lane, one PR.
Issues: S4 #887, S2 #888, S1 #889, S3 #890, S5 #891, S6 #892, S7 #893.
Source of the ask: the client's `Stock Balance 28 Aug 2026.xls` (sheets `Water Tap - Low`,
`Water Tap`, `Shower - Low`, ... ; low-sheet columns Item Code, Description, BRW Qty, Reorder
Level, Reorder Qty, Incoming Qty `TLLU8306312 - 180 nos`, PO Qty `202608-S0084 - 300 nos`,
Supplier, Remarks, Dealer o/s Qty).

## The problem, measured (local 0907 prod copy, 14 Sep 2026)

The order sheet already prints 13 of the client's 16 facts, frozen per run in
`scm.order_summary_row`. Three gaps and one universe problem:

| Gap | Today | Measured |
| --- | --- | --- |
| Container in the incoming cell | `site_pool_supply.open_spo_by_product` groups by `spo_number` only; `_docs_text` prints `SPO-2026/08-0085 - 200` | 920 open SPO allocations; 395 sit on an `inbound_shipments` row with `shipping_container_number`, 525 not loaded yet; `spo_allocations.container_number` itself is set on 14 |
| Description / Category / Reorder qty columns | not on `_EXPORT_COLUMNS` | `products.description` (14,782 of 14,791 active products; `product_name` is the code repeated), `product_categories.category_code` (118 codes, 0 null), `products.reorder_quantity` (3,882 set, blank otherwise) |
| A low-stock cut | export drops hidden covered rows and prints the rest; no "below level" sheet | client's own rule = raw BRW qty < level (336 low rows, 2 hand outliers, 11 qualifying rows omitted by hand) |
| Run universe | unscoped run admits only products with committed demand in the horizon (rule G1, `reorder_run_service.py:892-898`) | 950 of 14,789 plannable products; 7,778 products sit below level, 582 in the last run, **7,196 missing**; of those 5,527 have zero pool stock and 6,470 no outbound movement in 12 months |

A report bounded by the run therefore misses CB100-BL-DIY (87 on hand, level 100, dealer o/s
0, no open SO). Admitting every non-discontinued product (owner's first thought) puts 14,789
products in every run: ~60 s a run at the measured 4 s per 950, and ~7,000 buy rows for
SKUs nobody sells. Owner ruling 14 Sep: **dead guard** instead.

## Owner rulings (14 Sep 2026, chat)

1. Report bounded by a run; suggested qty comes from the engine. Chat ALWAYS creates a fresh run.
2. Two sheets: "Low stock" (raw pool on hand < level) and "All" (every planned product, hidden included). Pool total only.
3. Category column = `products.category_id` -> `category_code`. Description = `products.description` (owner, lavish 14 Sep: `product_name` holds the code). Reorder qty = `products.reorder_quantity` only (owner, lavish 14 Sep: not the buyer's `scm.reorder_level.reorder_qty`).
4. Container INTO the shared incoming cell; the order sheet changes too.
5. Admission = committed > 0 OR (below level AND not dead). Dead = existing `dead_stock_days` rule.
6. Chat filters: warehouses, products, date range. No category scope (backlog).
7. Over the chat turn budget: the worker pushes the file to the contact when ready.
8. Chat access = one new per-contact reveal key. Chat runs listed with a "via chat" marker.
9. Entry point on the plan view Actions menu, beside the order sheet items.

## Design - simplest thing that works

### S1 - engine admission, second leg (`app/services/scm/reorder_run_service.py`)

`_planning_rows` (L731) builds `product_admit_join` at L892-898 as
`JOIN (SELECT DISTINCT product_id FROM cv_all WHERE COALESCE(committed,0) > 0) admitted_product`.
It becomes a UNION of two legs, still `JOIN`ed on `keys.product_id`, still only when
`product_ids is None` (G10 untouched, L1005-1008 stamp unchanged):

```sql
JOIN (
    SELECT DISTINCT product_id FROM cv_all WHERE COALESCE(committed, 0) > 0
    UNION
    SELECT lvl.product_id
    FROM (
        SELECT p.id AS product_id,
               COALESCE(rl.level, NULLIF(p.reorder_level, 0)) AS level
        FROM products p
        LEFT JOIN scm.reorder_level rl
               ON rl.product_id = p.id AND rl.warehouse_id IS NULL
              AND rl.level > 0 AND rl.source = ANY(:rl_sources)
        WHERE p.is_active AND p.is_discontinued = false AND p.exclude_from_planning = false
    ) lvl
    JOIN (
        SELECT s.product_id, SUM(s.quantity_on_hand) AS pool_on_hand
        FROM stock s JOIN warehouses w ON w.id = s.warehouse_id
        WHERE w.counts_as_available AND {ACTIVE_SITE_POOL_SQL}
        GROUP BY s.product_id
    ) oh ON oh.product_id = lvl.product_id
    JOIN (
        SELECT product_id, MAX(day) AS last_day FROM scm.consumption_v GROUP BY product_id
    ) mv ON mv.product_id = lvl.product_id
    WHERE lvl.level IS NOT NULL
      AND oh.pool_on_hand < lvl.level
      AND mv.last_day >= (CURRENT_DATE - :dead_days)
) admitted_product ON admitted_product.product_id = keys.product_id
```

- `:rl_sources` = `rl_service.VALID_SOURCES` (the same "only a person's row is an override,
  0 is not a level" rule `_product_level` L1299-1340 applies in Python; the leg tests the
  SAME level the engine will plan against).
- Pool on hand = `_pool_on_hand_map`'s predicate (`stock` at active site pool with
  `counts_as_available`), so "below level" here is the same figure the Low sheet filters on.
- `:dead_days` = `reorder_policy.resolve_global_dead_stock_days(db)` else
  `DEFAULT_DEAD_STOCK_DAYS` (180). **Global only.** `dashboard_service._dead_days_for` also
  honours sku / product_class scoped rows; the admission leg does not. Trigger for adding
  the scoped lookup: the first `scm.reorder_policy` row with `scope_type <> 'global'` and a
  `dead_stock_days` on the prod copy (today there are none). A product with no
  `consumption_v` row is dead (no `mv` match), matching `_compute_status`'s
  `last_movement is None -> dead`.
- No zero-stock exemption: `_compute_status` says stockout before dead, but a stockout that
  has not moved in 180 days is still a SKU nobody sells; the owner's ruling was to keep
  those out.
- Rewrite the G1 comment block (L849-891) to state both legs. `tests/scm/
  test_reorder_committed_universe.py:60` stays green (fixture: stock 500 above level 100).
- Company scope: the leg's subqueries aggregate by `product_id`; `keys` is already filtered
  by the `cp*`/`cw*` predicates in `where` (L791-814), and a product id belongs to one
  company, so the join cannot leak a row across companies. Say so in the comment.
- Evidence run (AC-17) recorded under `evidence/low-stock-report/`. MEASURED 14 Sep on the
  0907 copy, superseding this plan's earlier "~1,600 products" estimate: an unscoped run
  goes from 950 products / 950 recs / 374 buys / 4.1 s to **2,017 products / 2,017 recs /
  1,151 buys / 8.5 s** (1,433 products are below level and still moving, 366 of them also
  carry committed demand; leg 2 alone finds 2,697 below level and the dead guard drops
  1,264 of them). The 15 s ceiling and the 5,000-row workbook cap both hold.

### S2 - container in the incoming cell (`app/services/scm/site_pool_supply.py`, `summary_order_service.py`)

- `open_spo_by_product` (L92-120): add
  `func.coalesce(func.nullif(SPOAllocation.container_number, ''), InboundShipment.shipping_container_number)`
  to the SELECT and GROUP BY (the `InboundShipment` outer join is already there). Rows become
  4-tuples `(pid, spo_number, container, qty)`.
- `open_po_by_product` (L60-89): SELECT `NULL AS container` so both callers hand
  `_grouped_supply_map` (L27-57) 4-tuples. The doc entry is `{"number", "qty"}` plus
  `"container": <str>` only when not NULL. Sort key stays `(number, container or "")`.
- `_docs_text` (summary_order_service L1303-1315): line =
  `f"{d['number']} - {d['container']} - {qty}"` when `d.get("container")` else the current
  shape. PO lines unchanged by construction.
- `write_rows` freezes the new key inside `incoming_spo_docs` (L347-353, no code change);
  runs frozen before this slice print the old shape (AC-23). No migration.
- Tests to extend: `tests/scm/test_order_summary_supply_docs.py` (`:106`, `:171`, `:200`).

### S3 - the workbook (`app/services/scm/low_stock_report_service.py`, new)

A sibling module, not more lines in the 3,085-line `summary_order_service.py`. It imports
the builders it reuses: `report`, `_qty_text`, `_ddmmyyyy`, `_docs_text`, `_remarks_text`,
`_xlsx_safe_text`, `_today`, `AppException`.

- `LOW_STOCK_COLUMNS` (16): Item code, Description, Category, BRW on hand, Reorder level,
  Reorder qty, Suggested qty, Suggestion, Order qty, Dealer o/s, Supplier, BRW PO qty,
  BRW incoming qty, Last in qty, Last in date, Remarks. `_EXPORT_COLUMNS` is not touched
  (two tests pin it).
- `export_low_stock(db, *, run_id, include_supplier=True) -> (bytes, content_type, filename)`:
  1. `rep = report(db, run_id=run_id)`; NO hidden-row drop (AC-33).
  2. Master joins by `product_code` in ONE batch query over `Product` outer-joined to
     `ProductCategory`: `Product.description`, `ProductCategory.category_code`,
     `Product.reorder_quantity` (blank when NULL or 0) (AC-34).
  3. Low rows = `pool_on_hand is not None and reorder_level is not None and pool_on_hand < reorder_level`
     (AC-32). Sort both sheets by `(category_code or "", product_code)`.
  4. `len(all_rows) > MAX_LOW_STOCK_ROWS (5000)` -> `AppException(422, "Narrow the plan first")`.
  5. Render: lift `_render_export_xlsx`'s body (L1519-1560) into a shared
     `write_sheet(ws, columns, rows, widths)` in `summary_order_service` and call it twice
     (`"Low stock"` first so `wb.active` tests keep reading the first sheet, then `"All"`).
     `include_supplier=False` drops the Supplier column from both tuples.
  6. Filename `low-stock-<as_of ddmmyyyy>.xlsx`.
- Route: `app/api/v1/scm/order_summary.py` L116-200 accepts `format in ("pdf","xlsx","low_stock_xlsx")`.
  For the new value: `kind = "low_stock_xlsx"`, filename as above, guard = its own
  `low_stock_guard_stats` (total frozen rows, NOT minus hidden, against
  `MAX_LOW_STOCK_ROWS`), enqueue `generate_low_stock_report(download_id, run_id, user_id)`
  on `imports`, `job_timeout=600`. `_EXPORT` (real user) unchanged for this path.
- Task: `app/tasks/export_tasks.py` `generate_low_stock_report(download_id, run_id, user_id, *, include_supplier=True)`
  mirroring `generate_order_sheet` L501-579 (scope dance, `mark_processing`, upload to
  `exports/low-stock/{download_id}/{filename}`, `mark_ready`, `_record_failure`). The push
  step (S5) lives at the tail of this same task behind the claim update, and the `except`
  branch takes the SAME claim to text the contact "Could not build the low stock report -
  ask again in a minute." (reviewer round 3 item 1): with the wait capped at 7 s a whole-book
  ask nearly always answers `pending` first, so a render failure after that point otherwise
  leaves a promise nobody keeps. `export_low_stock` returns the row counts with the bytes, so
  the task reads the frozen run ONCE (reviewer round 3 item 4; `row_counts()` is gone).

### S4 - frontend (Phase 1 first, against the mock)

- `services/summaryOrderService.ts`: new `exportLowStockReport(runId): Promise<MyDownload>`
  posting `{run_id, format: "low_stock_xlsx"}` to the SAME endpoint (the existing test at
  `:88-95` strict-equals the order sheet body, so a new function, not a new field). Contract
  doc block gains a section 6 with the request/response shapes above.
- `hooks/useSummaryOrder.ts`: `useExportLowStockReport(runId)` = `useExportOrderSheet` with
  the toast "Preparing the low stock report - it will appear in My Downloads."
- `components/ReorderPlanView.tsx` L93-131: third item `{key: 'low_stock_xlsx', label: 'Low
  stock report (Excel)', icon: FileSpreadsheet, disabled: either mutation pending}` after
  `order_sheet_xlsx`; add the mutation to the `useMemo` deps.
- `components/my-downloads/DownloadRow.tsx` L35-44 `KIND_LABEL`: add `order_sheet_pdf:
  'Order sheet PDF'`, `order_sheet_xlsx: 'Order sheet Excel'`, `low_stock_xlsx: 'Low stock
  report'` (the first two are missing today and render raw).
- Plans list marker: `services/reorderRunService.ts` `ReorderRunHistoryItem` gains
  `requested_via?: 'chat' | null`; `components/ReorderRunsGrid.tsx` L119-144 renders
  `<Badge variant="secondary" appearance="light" size="sm">via chat</Badge>` beside `daily`
  / `superseded`. Mock store returns one chat run.
- Settings field (AC-7): `app/(protected)/user-management/settings/chatbot-media/page.tsx` +
  its `services/chatbotMediaSettingsService.ts` already carry `media_sync_wait_seconds`; add
  `low_stock_sync_wait_seconds` beside it (label "Low stock report chat wait (seconds)",
  5..90), mocked in Phase 1, real in S5.
- Tests: `ReorderPlanView.lowStock.test.tsx`, one case in `summaryOrderService.test.ts`, a
  badge case in `ReorderRunsGrid.test.tsx`, one settings case; amend
  `ReorderPlanView.orderSheet.test.tsx:101` if its menu assertion is exhaustive.

### S5 - the chat route (`app/api/v1/scm/low_stock_report.py`, new; migration)

**Method is GET.** The MCP compiler injects `view=render` only on tools with no
`body_params` (`server.py:1604-1612`), and the chatbot lane sends `view=render` on every
call; a POST tool would never reach the presenter. `ToolSpec.read_only` already states
"METHOD IS TRANSPORT, NOT SEMANTICS", and `crm_portal_link_get` is the precedent for a tool
that mints an artefact and sits on the read list. Trigger to revisit: the compiler learns
optional query params on body tools.

`GET /api/v1/scm/low-stock-report` (`async def`, own router mounted in `scm/__init__.py`):

- Query: `warehouse_codes`, `product_codes` (csv / repeated, the outstanding report's
  parsing), `date_from`, `date_to`, `contact_id`, `space_id`. `contact_id` + `space_id`
  REQUIRED (422). Dependency `require_permission_with_api_key("scm.reorder.run")`.
- **Second gate** (the `require_permission_with_api_key` docstring's rule for anything that
  writes): resolve the contact via `head.access._resolve_contact_with_null_workspace_fallback`
  and read `contact_field_reveal_service.granted_keys`; without `scm.low_stock_report` ->
  403 `low_stock_report_not_enabled`, nothing written. `include_supplier =
  "purchase_orders.supplier" in keys`. Docstring names this as the gate and the reason the
  route may write under an API key.
- Owner of the run and the download row = the CRM user linked to the chatting contact:
  `users.respond_contact_id == <resolved respond_contacts.id>` (18 users carry the link on
  the prod copy; `respond_link_service` documents the same FK). Found -> that user's id is
  `actor` and `user_id`, so the file lands in THEIR My Downloads and the run says who asked.
  Not found -> the act-as user (`EXTERNAL_API_KEY_ACT_AS_USER_ID`), the file still reaches
  the contact over chat.
- Fast path, one thread (`asyncio.to_thread`, the `media.py:115-141` "copy everything out
  before the wait" rule): `create_run(..., actor=owner_user_id, enqueue=False,
  requested_via="chat", refuse_if_in_flight=True)` (new kwargs, new column); the
  `run_in_progress` 409 maps to `{status: "busy", reason: "in_flight"}` and the per-contact
  rate limit to `reason: "rate_limited"` (AC-49); `DownloadService.create(kind="low_stock_xlsx",
  user_id=owner_user_id, source_entity_type="reorder_run", source_entity_id=run_id,
  filename=...)`; `run_job = enqueue_job(run_reorder_job, run_id, queue_name="imports")`;
  `enqueue_job(generate_low_stock_report, download_id, run_id, user_id,
  include_supplier=..., queue_name="imports", job_timeout=600, depends_on=run_job)`
  (`enqueue_job` forwards `**kwargs` to `Queue.enqueue`, RQ honours `depends_on`).
- Wait: `_await_download(download_id)` polling `user_downloads.status` through short-lived
  sessions every 0.25 s, bounded by `asyncio.wait_for(..., <wait>)` where `<wait>` =
  `system_settings.low_stock_sync_wait_seconds` (owner ruling on the lavish page: a System
  Setting, not a constant). New column `Integer, nullable=False, server_default="40"`,
  validated 5..90 in the settings route the way `media_sync_wait_seconds` is
  (`app/api/v1/user_management/settings.py:148`), read live per request (no cache), exposed
  on the System Settings page beside the media wait, and added to BOTH manual dict builders
  (`get_me` is not involved; `system_settings` GET/PUT are). This is how long the route
  holds the chat turn open waiting for run + export before it answers "pending" and leaves
  delivery to the worker push.
- **The setting is CAPPED BY THE TRANSPORT TIMEOUT** (console round 3, 14 Sep, defect A -
  measured data loss). The effective wait is
  `min(low_stock_sync_wait_seconds, chatbot_mcp_timeout_seconds - 3)`, which is 7 s today.
  The chatbot lane's MCP client gives up after `settings.chatbot_mcp_timeout_seconds` (10 s
  default, `lanes/business/services.py`), which is SHORTER than the 40 s default: a full
  unscoped run (>10 s measured; 2-product 2.7 s, BRW-scoped 8.7 s) made the lane raise
  `httpx.ReadTimeout` and render its generic failure line while the route, still waiting,
  never reached its timeout branch and so never set `deliver_to_contact_id` - the worker
  built a workbook nobody delivered. Answering `pending` INSIDE the client's budget is what
  makes the claim happen. `chatbot_mcp_timeout_seconds` is deliberately NOT raised: it is
  every tool's knob. The MCP server's own CRM-facing timeout (`CRM_MCP_TIMEOUT`, default
  60 s, `sorento_crm_mcp/settings.py`) is far longer than either, so the LANE's client is
  the binding one; if it is ever lowered below this cap it becomes binding instead. The
  settings field says so in its hint (AC-7), because a value above the cap is silently
  ignored.
- Ready in time -> `{status: "ready", run_id, as_of, low_count, all_count, attachments:
  [{url, filename, mimeType, attachmentType: "file"}]}`. URL: R2 -> `cdn_base_url(provider,
  quote(key, safe="/"))`; S3 -> `get_signed_url(key, 7 days)` (the exact branch
  `upload_chat_attachment` L666-676 uses; the storage key already ends in the filename).
  `low_count`/`all_count` are written onto the download row by the task (two new nullable
  int columns, or read back from the workbook? -> **columns**: `row_count_low`, `row_count_all`,
  so the route never opens the file).
- Timed out -> claim: `UPDATE user_downloads SET deliver_to_contact_id = :rc WHERE id = :id
  AND status <> 'ready'`. 0 rows -> the row turned ready meanwhile -> return the ready shape.
  1 row -> `{status: "pending", run_id, download_id}`.
- Task tail (after `mark_ready`): `UPDATE user_downloads SET delivered_at = now() WHERE id =
  :id AND deliver_to_contact_id IS NOT NULL AND delivered_at IS NULL RETURNING
  deliver_to_contact_id`. 1 row -> `send_chat_attachment_for(db, identifier=<respond_io_id>,
  respond_contact_id=<rc>, attachment_type="file", url=<same URL rule>,
  business_table="user_downloads", business_id=download_id)`. `attachment_window_closed`
  (422) and `respond_send_failed` (502) are logged by `log_respond_send` and swallowed; the
  download row stays `ready`. Postgres row locks serialise the two conditional updates, so
  exactly one of {turn returns the file, worker pushes it} happens (AC-46).
- Migration (one file), **LANDS IN S3** so AC-36's row counts can go green there; S5 only
  uses it: `scm.reorder_run.requested_via VARCHAR(10) NULL`;
  `user_downloads.deliver_to_contact_id UUID NULL`, `delivered_at TIMESTAMP NULL`,
  `row_count_low INT NULL`, `row_count_all INT NULL`; `system_settings.low_stock_sync_wait_seconds
  INT NOT NULL DEFAULT 40`. `reorder_runs.py:417` `cols` string +
  `ReorderRunListItem` (`scm_reorder.py:135-178`) + the L316-345 row mapper gain
  `requested_via`; `ReorderRunStatusResponse` too.
- The act-as user (`EXTERNAL_API_KEY_ACT_AS_USER_ID`) must hold `scm.reorder.run`; DoD item.

### S6 - MCP tool, presenter, lane gate

- `sorento_crm_mcp/sorento_crm_mcp/catalog.py`: `ToolSpec("crm_low_stock_report", <desc>,
  "/api/v1/scm/low-stock-report", (), ("warehouse_codes", "product_codes", "date_from",
  "date_to", "contact_id", "space_id"), module="scm", domain="inventory",
  escalation_team="warehouse", restricted_fields=(("scm.low_stock_report", "Low stock report
  over chat"),))`. Description: always runs a fresh plan; resolve a location TOKEN to exact
  codes first; pass contact_id and space_id both; the COMPANY SCOPE paragraph verbatim from
  `crm_outstanding_report`.
- `server.py:31` `TOOL_REQUIRED_QUERY_HINTS["crm_low_stock_report"] = ("contact_id", "space_id")`.
- `presenters.py`: add to `PRESENTER_TOOLS`; branch in `present_response` beside L1556
  returning `_low_stock_envelope(data)`: `{result_type: "low_stock_report", response: <two
  lines | one line>, attachments: <passthrough>, has_result: True}` (AC-61 wording).
- **`has_result` is True on EVERY branch, the error one included** (accepted 14 Sep,
  refining reviewer S1/N6's "render it as a miss"): the console found that a `has_result:
  False` here routes the turn into the inventory domain's generic miss ("Could not find
  inventory - escalate to warehouse team?"), which is the wrong thing to say about a report
  that failed to build, so an error is a TERMINAL answer rendered verbatim like busy and
  pending, and the lane fragment carries `escalate` for any picker consumer. The lane's own
  transport failure (`LOW_STOCK_UNAVAILABLE_MESSAGE`) takes the same shape (AC-61c).
- Backend: `contact_field_reveal_service.FIELD_REVEAL_KEYS` + `("scm.low_stock_report", "Low
  stock report over chat")`; `mcp_tool_domains.CHATBOT_TOOL_DOMAINS["crm_low_stock_report"]
  = "inventory"`; `contracts.DOMAIN_SPEC["inventory"]`: `intents += ("low_stock_report",)`,
  `switch_words += ("low stock", "reorder report", "below level")`, `tools += ("crm_low_stock_report",)`
  (NOT `tools[0]`).
- `lanes/business/__init__.py::run_fetch`: when `parse_output["intent_hint"] ==
  "low_stock_report"`, swap the pick to `crm_low_stock_report` (the outstanding override's
  shape), then the gate before fetch mirroring L825-856 with `_LOW_STOCK_GRANT =
  "scm.low_stock_report"`: no grant -> refusal text `LOW_STOCK_NOT_ENABLED_MESSAGE = "Low
  stock report is not enabled for your account."` + the existing team picker, no fetch.
- `fetch.py`: `DATE_PARAMS["crm_low_stock_report"] = ("date_from", "date_to")`; branch in
  `entity_ids_transformer` beside L565: `warehouse_codes` from warehouse entities via the
  existing `resolve_warehouse_token` result (`semantic_input["low_stock_warehouse_codes"]`
  set in `__init__.py` the way `outstanding_warehouse_codes` is at L795-819),
  `product_codes` from product entities' `code`/`canonical_code`; `output_structurer` branch
  `_low_stock_report_output` mirroring L1517-1579 with `attachments` populated from the
  envelope (the outstanding one returns `[]`) so `engine._attachments_src` emits
  `send_attachments`.
- `app/services/low_stock_report_bootstrap.py` = `outstanding_report_bootstrap.py` with the
  new name; wired in `app/main.py` after L422.

### S7 - parser words

- `app/services/chatbot_parser_prompt.py`: new `LOW_STOCK_ADDENDUM` constant appended like
  `GROWTH_R1_ADDENDUM` (L102): intent `low_stock_report` for "low stock report", "low stock",
  "reorder report", "stock below level"; a location word is a `warehouse` entity, a product
  code a `product` entity, a date phrase fills `date_filter_start/end`. Golden fixtures for
  the four journey phrasings. `test_parser_prompt_is_live.py` / `test_parser_user_block_parity.py`
  stay green.
- `documentation/plans/chatbot/n8n-changes.md`: `## S-low-stock` with the standard seven
  sub-headings; the only operational step is granting the key.
- Console case `tests/chatbot/console_cases/2026-09-14-low-stock-report.yaml`.
- **Prompt registry (AC-74, found in Phase 3):** `ai_prompt_registry.render()` serves the
  PUBLISHED `chatbot_semantic_parser` version, so the addendum reaches the chatbot only
  through `alembic/versions/517_chatbot_low_stock_vocab.py` (mirror of 514: both bodies as
  new unlabelled versions, idempotent, `publish(session)` callable outside alembic). Locally
  the console check runs with `--prompt-version <new id>`; on prod the owner moves the
  `production` label in the admin UI after deploy. Post-deploy step, PR body.

## Slices and order

| Slice | Phase | Executor | Depends on |
| --- | --- | --- | --- |
| S4 FE mock (menu item, label, badge, settings wait field) | 1 | coder | - |
| S2 container in the incoming cell | 2 | tester -> coder | - |
| S1 admission second leg | 2 | tester -> coder | - |
| S3 workbook + export kind + the lane's one migration | 2 | tester -> coder | S2 |
| S5 chat route + migration + push | 2 | tester -> coder | S3 |
| S6 MCP tool + gate | 2 | tester -> coder | S5 |
| S7 parser words + console case | 2 | tester -> coder | S6 |
| Phase 3 review + security review + browser + console check | 3 | reviewer, security-reviewer, tester | all |

Security review is mandatory: API-key write route, per-contact gating, storage URL, raw SQL
over company-scoped tables.

## Testing seams (agreed before Phase 2)

- Engine: `svc.create_run(db, [...], enqueue=False)` + `svc.run_reorder(run_id, db=db)` on
  seeded products (the `test_reorder_committed_universe.py` fixtures `_mk_product`,
  `_mk_stock`, `_mk_movement`, `_mk_demand`, plus a `scm.consumption_v`-visible movement and
  a global `reorder_policy.dead_stock_days`).
- Workbook: `export_low_stock(db, run_id=...)` -> `openpyxl.load_workbook(BytesIO(bytes))`.
- Route: FastAPI TestClient with `X-API-Key`; RQ mocked (`enqueue_job` patched), the task
  called directly; `send_chat_attachment_for` patched; the two interleavings driven by
  ordering `mark_ready` vs the route's claim.
- MCP: `sorento_crm_mcp/tests` compile + presenter golden.
- Lane: `tests/chatbot/test_outstanding_lane.py::TestFieldRevealGateBeforeFetch` shape.

## Backlog (documentation/backlogs/backlog.md)

Category scope on runs; per-warehouse columns on the All sheet; PDF flavour; sku/class-scoped
dead days in admission; compiler support for optional query params on body tools.
