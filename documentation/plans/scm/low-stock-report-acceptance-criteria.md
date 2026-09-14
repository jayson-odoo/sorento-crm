# UAC - Low stock report: a run-bounded Excel on the plan, and over WhatsApp

Plan: `PLAN-low-stock-report.md` (same folder).
Owner rulings, 14 Sep 2026 (chat, from the client's `Stock Balance 28 Aug 2026.xls`): the report
is bounded by a run (the suggestion comes from the engine); two sheets only, "Low stock" (raw
pool on hand < level) and "All"; pool total only, no per-warehouse columns; Category column from
`products.category_id`; container number goes INTO the shared incoming cell (the order sheet
changes too); Description and Reorder qty columns on both sheets; the chat tool ALWAYS creates a
fresh run; runs created from chat are listed like any run with a "via chat" marker; run admission
gains a dead-guard leg (owner rejected "every non-discontinued product": 14,789 products, ~60s a
run, ~7,000 dead buy rows); if run + export outrun the chat turn budget the worker pushes the
file when ready; access over chat is one new per-contact reveal key.

## Journey

**Buyer, on the plan.** Procurement > Supply Chain > Reorder Planning > a run. Actions menu
shows "Low stock report (Excel)" beside "Order sheet PDF" and "Order sheet Excel". One click. A
toast says it is being prepared and will appear in My Downloads. The drawer shows it preparing,
then ready. The workbook has two sheets. "Low stock" lists every planned product whose BRW on
hand is below its reorder level. "All" lists every product the run planned, the comfortably
covered ones included. Both carry the same columns: Item code, Description, Category, BRW on
hand, Reorder level, Reorder qty, Suggested qty, Suggestion, Order qty, Dealer o/s, Supplier,
BRW PO qty, BRW incoming qty, Last in qty, Last in date, Remarks. The incoming cell now names the
container under each SPO, the way the client's sheet writes `TLLU8306312 - 180 nos`. Decisions
the buyer makes: none new.

**Staff, on WhatsApp.** Types "low stock report", or "low stock report BRW", or "low stock for
SRTWT7408 until 30 Nov". The bot says it is running a fresh plan for that scope. Within the turn
it sends the workbook as a document with one summary line (as-of, how many low rows). If the run
takes longer than the turn allows, the bot says the file is on its way and the worker sends it
the moment it is ready. A contact without the key reads "Low stock report is not enabled for
your account." The run the chat asked for appears in Reorder Planning marked "via chat", so the
buyer knows why it exists.

**The daily plan, once.** Products below their level that still move enter the run and get a
suggestion even with no open sales order. Dead products (no outbound movement inside
`dead_stock_days`) stay out unless a buyer names them.

## Phase 1 - frontend first, mocked

### Slice S4 - the menu item, the marker, the download label

- **AC-1 [FE]** Given a plan view, when the buyer opens Actions, then a third item "Low stock
  report (Excel)" sits directly under "Order sheet Excel", same icon family
  (`FileSpreadsheet`), disabled while any export is pending, exactly as the two order sheet
  items are.
- **AC-2 [FE]** Given the buyer clicks it, then the hook posts `{run_id, format: "low_stock_xlsx"}`
  to the SAME export endpoint the order sheet uses, invalidates `MY_DOWNLOADS_QUERY_KEY` and the
  run's entity-downloads key, and toasts "Preparing the low stock report - it will appear in My
  Downloads." On error the extracted message is toasted (`extractApiError`).
- **AC-3 [FE]** Given the My Downloads drawer shows a row of kind `low_stock_xlsx`, then its label
  reads "Low stock report" (not the raw kind), and the filename is `low-stock-<ddmmyyyy>.xlsx`.
- **AC-4 [FE]** Given the Reorder Planning list, when a run was requested from chat, then its row
  shows a `Badge` "via chat" in the existing run-identity column (no new column); a manual run
  shows nothing. The badge uses the existing secondary Badge variant; nothing animates.
- **AC-5 [UX]** At 375px the Actions menu still lists all three export items without clipping;
  at 1280px the plans list badge does not widen the column (column keeps its explicit `size`).
- **AC-7 [FE]** System Settings page shows "Low stock report chat wait (seconds)" beside the
  media sync wait, numeric input 5..90, saved through the existing settings mutation; mocked
  in Phase 1, wired in S5.
- **AC-6 [T]** Vitest: `ReorderPlanView.lowStock.test.tsx` asserts AC-1 and AC-2 (item present,
  disabled while pending, service called with `low_stock_xlsx`, toast text);
  `summaryOrderService.test.ts` gains one case for the new format value; the runs grid test
  asserts AC-4 for a run with and without the marker.

## Phase 2 - backend, test-first

### Slice S1 - the engine admits live products below level (dead guard)

- **AC-10 [BE]** Given an UNSCOPED run (no `product_codes`) and a product with zero committed
  demand in the horizon, a resolved level L (buyer's product-wide `scm.reorder_level` with
  `source in (manual, accepted_suggestion)`, else `products.reorder_level`), site-pool on hand
  < L, and an outbound movement inside the resolved `dead_stock_days`, when the run completes,
  then that product has a recommendation row with `policy_type = reorder_level` and
  `rec_type = buy`, sized `L - net` floored at MOQ and ceiled to order multiple, exactly as a
  committed-demand product on the level basis would.
- **AC-11 [BE]** Same product but its last outbound movement is older than `dead_stock_days`
  (or it never moved), then it has NO recommendation row in the run.
- **AC-12 [BE]** Same product but site-pool on hand >= L (not below level) and zero committed
  demand, then it has NO recommendation row (the committed-demand leg is unchanged).
- **AC-13 [BE]** A product with zero committed demand and NO resolvable level (neither buyer
  row nor master) is NOT admitted by the new leg (a `needs_level` row needs a demand signal,
  as today).
- **AC-14 [BE]** A NAMED product (`product_codes` given) is admitted regardless of demand, level
  or movement (rule G10 unchanged).
- **AC-15 [BE]** "Dead" reuses the dashboard's rule: the same last-outbound-movement source and
  the same `reorder_policy.dead_stock_days` resolution `dashboard_service._dead_days_for` uses.
  No second definition of dead.
- **AC-16 [BE]** The G1 comment block in `reorder_run_service` is rewritten to state the two
  legs; the existing admission tests stay green.
- **AC-17 [BE]** Evidence (not a test): an unscoped run on the 0907 copy before/after, recorded
  in `evidence/low-stock-report/README.md`: planned_count, recommendation count, wall time.
  Measured 14 Sep 2026 (this line carried an estimate of ~1,600 products before the run):
  950 -> **2,017** products, 950 -> 2,017 recommendations, 374 -> 1,151 buys, wall time
  4.1 s -> **8.5 s**, inside the 15 s ceiling.

### Slice S2 - the incoming cell names the container

- **AC-20 [BE]** `site_pool_supply.open_spo_by_product` groups by `(spo_number, container)`
  where container = `COALESCE(NULLIF(spo_allocations.container_number, ''),
  inbound_shipments.shipping_container_number)`; each doc entry carries
  `{"number", "container", "qty"}`; `qty` totals are unchanged.
- **AC-21 [BE]** `_docs_text` prints one line per doc: `<SPO number> - <container> - <qty>` when
  a container is known, `<SPO number> - <qty>` when not. The first line stays the total. PO
  docs (no container) print exactly as before.
- **AC-22 [BE]** The order sheet PDF and Excel both show the new line shape in "BRW incoming
  qty"; every other cell is byte-identical to before on the same frozen run (golden test on a
  seeded run: one allocation with a shipment container, one without, one PO line).
- **AC-23 [BE]** `order_summary_row.incoming_spo_docs` frozen by `write_rows` carries the
  container key; a run frozen BEFORE this slice (docs without the key) still prints via the
  no-container shape. No migration.

### Slice S3 - the low stock workbook

- **AC-30 [BE]** `POST /api/v1/scm/order-summary/export` accepts `format: "low_stock_xlsx"`
  (alongside `pdf` / `xlsx`), creates a `user_downloads` row of kind `low_stock_xlsx` with
  filename `low-stock-<as_of ddmmyyyy>.xlsx`, `source_entity_type = reorder_run`, and enqueues
  `generate_low_stock_report(download_id, run_id, user_id)` on the `imports` queue. One in
  flight per user per run per kind (409 otherwise), same as the order sheet.
- **AC-31 [BE]** The workbook has exactly two sheets, in order: "Low stock", "All". Columns on
  both, in order: Item code, Description, Category, BRW on hand, Reorder level, Reorder qty,
  Suggested qty, Suggestion, Order qty, Dealer o/s, Supplier, BRW PO qty, BRW incoming qty,
  Last in qty, Last in date, Remarks. Header row frozen and styled as the order sheet's;
  quantities are numbers; text cells pass `_xlsx_safe_text`.
- **AC-32 [BE]** "Low stock" rows = report rows where BOTH `pool_on_hand` and `reorder_level`
  are non-null AND `pool_on_hand < reorder_level`, hidden-by-default rows INCLUDED (a covered
  row can still be below raw level), sorted by Category then Item code.
- **AC-33 [BE]** "All" rows = every row `report()` returns for the run, hidden-by-default rows
  included, same sort. The order sheet export keeps dropping hidden rows (unchanged).
- **AC-34 [BE]** Description = `products.description` (NOT `product_name`, which repeats the
  code); Category = the product's `product_categories.category_code`; Reorder qty =
  `products.reorder_quantity`, blank when NULL or 0. All three are joined at export time
  (master data, not frozen figures); every other column reads the frozen row exactly as the
  order sheet does.
- **AC-35 [BE]** Row cap for this kind is its own constant `MAX_LOW_STOCK_ROWS = 5000` applied
  to the "All" sheet; above it the route refuses with 422 "Narrow the plan first". The order
  sheet's `MAX_EXPORT_ROWS = 2000` is untouched.
- **AC-36 [BE]** The task mirrors `generate_order_sheet`: read the run under no scope, adopt its
  company, `mark_processing` -> render -> upload to
  `exports/low-stock/{download_id}/{filename}` -> `mark_ready`; `_record_failure` on any
  exception; caller scope restored in `finally`.
- **AC-37 [T]** pytest on a seeded run: two sheets, header tuple, Low membership (one below,
  one at level, one above, one with null level), All count, Description/Category/Reorder qty
  values, filename, kind, 409 on second in-flight, 422 over cap.

### Slice S5 - the chat route: fresh run, wait, deliver or hand to the worker

- **AC-40 [BE]** `GET /api/v1/scm/low-stock-report` accepts `X-API-Key` via
  `require_permission_with_api_key("scm.reorder.run")`, query params `warehouse_codes?`,
  `product_codes?` (csv or repeated), `date_from?`, `date_to?`, `contact_id`, `space_id`.
  `contact_id` + `space_id` are REQUIRED here (the route is for the chatbot only); 422
  without. GET, not POST: the MCP compiler injects `view=render` only on query-param tools
  (plan S5).
- **AC-41 [BE]** The route resolves the contact and reads its reveal keys. Without
  `scm.low_stock_report` it returns 403 `{code: "low_stock_report_not_enabled"}` and creates
  NO run and NO download row.
- **AC-42 [BE]** With the key, it creates a run via `reorder_run_service.create_run` with the
  given scope (empty lists = all), horizon dates when given, `requested_via = "chat"`
  (new nullable column on `scm.reorder_run`, values `chat` or NULL; migration) and
  `actor` = the CRM user whose `users.respond_contact_id` is the resolved contact (else the
  act-as user), then creates the download row (kind `low_stock_xlsx`, same user, so the file
  appears in THAT user's My Downloads) and enqueues the run job and the
  export job so the export runs after the run completes (RQ `depends_on`, or the export task
  polls the run status with the same 600 s job timeout; the plan names which).
- **AC-43 [BE]** The route waits up to `system_settings.low_stock_sync_wait_seconds` (new
  column, default 40, validated 5..90 on PUT like `media_sync_wait_seconds`, read live, shown
  on the System Settings page beside the media wait, present in the settings GET/PUT dict
  builders) polling the download row. The task writes `row_count_low` / `row_count_all` onto the row at
  `mark_ready` so the route never opens the file. When it turns `ready` in time, the
  response is `{status: "ready", run_id, as_of, low_count, all_count, attachments: [{url, filename,
  mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  attachmentType: "file"}]}`. `url` is the R2 CDN URL (permanent, unsigned) when the provider is
  R2, else a 7-day signed URL; the filename is the URL's last path segment.
- **AC-44 [BE]** When the budget lapses first, the route claims delivery for the worker with a
  single conditional update on the download row: `deliver_to_contact_id = <respond_contacts.id>
  WHERE id = :id AND status <> 'ready'`. If that update touches 0 rows the row is already ready
  and the route returns the `ready` shape instead. Otherwise it returns
  `{status: "pending", run_id, download_id}`.
- **AC-45 [BE]** After `mark_ready`, the export task claims the push with one conditional
  update: `delivered_at = now() WHERE id = :id AND deliver_to_contact_id IS NOT NULL AND
  delivered_at IS NULL`. Only when that touches 1 row does it call
  `respond_chat_template_service.send_chat_attachment_for` for that contact with the CDN URL;
  the send logs its outbox row. A closed 24 h window surfaces as the existing
  `attachment_window_closed` outcome in the log, never an exception into RQ.
- **AC-46 [BE]** The two conditional updates make the outcome exactly one of: the turn returns
  the attachment, or the worker pushes it. Test both interleavings (worker ready before the
  route's claim; route's claim before ready).
- **AC-47 [BE]** The Supplier column is omitted from the workbook when the contact lacks the
  `purchase_orders.supplier` reveal key (the route passes `include_supplier` into the task);
  the plan-view export (AC-30) always includes it.
- **AC-48 [BE]** New migration adds `scm.reorder_run.requested_via`,
  `user_downloads.deliver_to_contact_id`, `delivered_at`, `row_count_low`, `row_count_all`, and
  `system_settings.low_stock_sync_wait_seconds`;
  `requested_via` reaches the FE in the run list/detail schema (both serializers, plus the
  `cols` string the list reads), and `list_my_downloads` is unchanged.
- **AC-49 [BE]** Runs created here obey the existing one-in-flight rule for runs (409 while a
  run is `queued`/`running` for the company); the route maps that 409 to
  `{status: "busy"}` so the bot can say a plan is already running.
- **AC-50 [T]** pytest: 422 without contact, 403 without key (no rows created), ready path
  shape, pending path + worker push (mock `send_chat_attachment_for`), both interleavings,
  supplier omission, busy mapping, owner resolution (linked user -> their My Downloads;
  unlinked contact -> act-as user).

### Slice S6 - the MCP tool and the lane gate

- **AC-60 [MCP]** `catalog.py` gains `crm_low_stock_report`: GET
  `/api/v1/scm/low-stock-report`, `query_params = (warehouse_codes, product_codes,
  date_from, date_to, contact_id, space_id)`, `module = "scm"`, `domain = "inventory"`,
  `escalation_team = "warehouse"`, `restricted_fields = (("scm.low_stock_report", "Low stock
  report over chat"),)` (the pinned-keys test shape), description stating: always runs a
  fresh plan; resolve location tokens to exact codes first; pass contact_id and space_id
  both.
- **AC-61 [MCP]** The presenter renders `ready` as two lines (`Low stock report - as of
  <dd/mm/yyyy>` and `Low: <n> of <m> planned products`) plus `attachments[]` carrying the
  route's entry unchanged; `pending` as one line ("Preparing the low stock report - it will be
  sent here when ready."); `busy` as one line ("A plan is already running - try again in a
  minute."). No UUID in any line.
- **AC-62 [MCP]** `PRESENTER_TOOLS`, `mcp_tool_domains.CHATBOT_TOOL_DOMAINS`, backend
  `contracts.DOMAIN_SPEC[<domain>].tools` and `fetch.DOMAIN_CLAIMED_TOOLS` all list the tool;
  the pinned-set CI test stays green. `read_only` follows the `crm_portal_link_get` precedent
  (POST that mints an artefact, allowed on the chatbot list) and says so in its docstring.
- **AC-63 [BE]** `FIELD_REVEAL_KEYS` gains `("scm.low_stock_report", "Low stock report over
  chat")`; the pinned-keys test passes; the admin field-reveal UI lists it with no code change
  beyond the tuple.
- **AC-64 [BE]** In the business lane, an ask that parses to the low stock intent from a contact
  WITHOUT `scm.low_stock_report` is refused BEFORE any fetch with the literal
  "Low stock report is not enabled for your account." and ends with the existing team picker,
  the same shape as `SO_NOT_ENABLED_MESSAGE`. No run is created.
- **AC-65 [BE]** `outstanding_report_bootstrap`'s sibling appends `crm_low_stock_report` to
  `ai_assistant_configs.enabled_tools` at startup, idempotently.
- **AC-66 [T]** MCP tests: tool compiled with the six body params, presenter three shapes,
  attachments passthrough. Backend chatbot tests: gate refusal (no fetch), grant path calls the
  tool with `warehouse_codes` from a location entity, `product_codes` from a product entity,
  `date_from/date_to` from the parser dates.

### Slice S7 - the parser knows the words

- **AC-70 [BE]** Parser intent enum gains `low_stock_report`; prompt lists trigger phrases
  ("low stock report", "low stock", "reorder report", "stock below level") and states that a
  location word scopes warehouses, a product code scopes products, and a date phrase sets the
  horizon. Golden parser fixtures cover the four journey phrasings.
- **AC-71 [BE]** `fetch.DATE_PARAMS` maps the tool to `date_from`/`date_to`;
  `entity_ids_transformer` fills `warehouse_codes` from warehouse entities (exact codes after
  the existing token resolution) and `product_codes` from product entities.
- **AC-72 [BE]** `documentation/plans/chatbot/n8n-changes.md` gains a section: no n8n node
  change (attachments ride the existing `send_attachments` action); the only operational step
  is granting `scm.low_stock_report` to staff contacts.
- **AC-73 [E2E]** Console check case `tests/chatbot/console_cases/low_stock_report.yaml`:
  granted contact gets an xlsx attachment or the pending line; ungranted contact gets the
  refusal. Recorded agent-browser run: plan view Actions -> Low stock report -> My Downloads
  shows it ready; open the file, two sheets, container in the incoming cell.
- **AC-74 [BE]** Migration `517_chatbot_low_stock_vocab` publishes BOTH parser prompt
  bodies carrying `LOW_STOCK_ADDENDUM` as new UNLABELLED `chatbot_semantic_parser`
  versions (idempotent on template text, `seed_prompt_registry` first, insert in a
  module-level `publish(session)`), because `ai_prompt_registry.render()` reads the
  published version and never the Python constant - without it the words reach no live
  turn. The owner promotes the `production` label after deploy: a POST-DEPLOY step,
  recorded in `n8n-changes.md` S-low-stock Step 2 and in the PR body, and no label is
  moved by the migration itself.

## Not in scope (backlog)

- Category as a run scope ("water tap low stock"): needs a category filter on runs.
- Per-warehouse quantity columns on the "All" sheet.
- PDF flavour of the low stock report.

## No-motion list

Actions menu item, the "via chat" Badge, the My Downloads label: static. Existing drawer
transitions unchanged.
