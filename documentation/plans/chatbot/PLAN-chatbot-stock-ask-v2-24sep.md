# PLAN - Chatbot stock ask v2: four-branch answer on #1118's verdict step, X cap, Y ETA offset, salesman notification, asks record

Status: grilled 24 Sep 2026, ready for tickets. Track: full feature (four migrations, one new permission family, one new table, a portal page). Nothing built.
Issue: #1168. Grill: owner rulings R1 to R11 of 24 Sep 2026 (quoted below, binding; they override the pre-grill draft).
UAC: `chatbot-stock-ask-v2-24sep-acceptance-criteria.md`
Depends on: PR #1118 (`feat/chatbot-dealer-stock-verdict`, open) rebased onto main and merged (slice S0); PR #1177 (`feat/customer-sales-agent-assignment`, open, #1170 slice 1) merged before S4.
Classification: the X / Y columns, the contact toggles and the `stock_asks` table are CORE in `public` (they extend `product_categories`, `products`, `respond_contacts`, `customers`); the branch decision lives in the stock balance read #1118 already extends (`app/services/inventory_service.py`), the notification and the ask write live in the `chatbot` module package (`app/services/chatbot/`), the Respond send in `app/tasks/`.

## Rulings (owner, grill of 24 Sep 2026, quoted verbatim)

> R1 Scope: contacts whose stock visibility policy mode is "Availability only". v2 is a change to PR #1118's verdict step (branch feat/chatbot-dealer-stock-verdict, feat: dealer stock verdict): keep #1118's per-product quantity collection (Focus.tasks, StockQtyTask) and replace its answers with the four branches below. The old stock_denied / demand_qty path on the chatbot_stock_denial_enabled flag stays exactly as is for stock-denied contacts. #1118 must be rebased onto main and merged before v2 slices start; the plan states that as slice 0.
>
> R2 X and Y: plain nullable integer columns on product_categories and products (X = max quantity the AI may answer for; Y = days added to the shipment ETA). Product value overrides the category value when set; only the product's own category, never a parent. Unset means 0: no X means the AI cannot answer any quantity for that product (opt-in per category), no Y means 0 days. Editing X and Y is gated by a new permission slug from the _crud pattern; shown on the category form and the product form, view = edit layout.
>
> R3 Location scope: the asking contact's stock visibility policy locations (site pool), the same set #1118 uses. No new column on customers.
>
> R4 "Got stock" = #1118's available (on hand in the policy locations minus what sales orders reserve) covers Q.
>
> R5 ETA source: the earliest still-incoming inbound_shipments row (shipment_status != draft, a line for the product with line_status != received and quantity_shipped - quantity_received > 0) that has a packing list (attachment_id IS NOT NULL), ordered by estimated_arrival_date asc nulls last, ANY location. Never eta_delay_date, never spo_allocations, never purchase orders. Answer date = estimated_arrival_date + Y, formatted dd/mm/yyyy. #1118's incoming and purchase reads and its "purchase, ETA in N days" wording are removed from this path.
>
> R6 Branches after quantity Q for product P is known:
> B1 Q > X, or X unset: "The quantity is more than what I can confirm here, please refer to your salesman" (polite, professional). Never reveal stock. Notify the agent; when X is unset the agent notification reason reads "no cap set for <category>".
> B2 Q <= X and available covers Q: "Yes, we have stock for <P> x Q, please refer to your salesman to proceed". Notify the agent.
> B3 Q <= X, not covered, a shipment per R5 exists: "No stock at the moment, ETA dd/mm/yyyy" (date + Y). No notification. Attach the shipment's packing list only when the contact's packing_list_allowed toggle is on; otherwise no attachment and no quantities.
> B4 Q <= X, not covered, no shipment per R5: "No stock and no incoming at the moment, please refer to your salesman". Notify the agent.
>
> R7 Per-contact toggles on respond_contacts: notify_salesman (default off) and packing_list_allowed (default off), on the contact form.
>
> R8 Notification: customer -> customers.sales_agent_id -> sales_agents.contact_id -> Respond.io. One use case stock_ask_salesman, one template with an outcome phrase slot (in stock / too big / no stock no incoming / no cap set) and the ask facts (customer, contact, product, quantity, time). Sent through send_text_or_template (template outside the 24h window, plain text following the template wording inside it). Each send writes its integration_log row. No agent or no agent contact: record the ask, skip the send, log the skip reason.
>
> R9 Asks record ("Asks"): a new table, one row per stock ask answered by v2: customer, contact, product, quantity, branch, answer summary, notified_agent (bool + reason when skipped), state open / done, note (free text), timestamps. Surfaces: CRM customer detail page "Asks" tab worked by the office (state + note editable, RBAC via the customers edit permission); portal page "Customer asks" for the sales agent's linked contact, listing asks for customers assigned to that agent, same state + note, using the portal DataGrid pattern (PortalLanding) and the debtors-for-agent resolution. Portal page is the LAST slice. Opportunity link comes with #1170 later (one nullable column then).
>
> R10 Detailed and Compact mode contacts are unchanged by v2.
>
> R11 Dependencies: PR #1177 (customer sales agent picker, slice 1 of #1170) gives the customer -> agent link; #1118 gives quantity collection and the availability read.

What these rulings retire from the pre-grill draft: `customers.stock_warehouse_id` (R3), any change to the `stock_denied` / `demand_qty` arm (R1), `COALESCE(eta_delay_date, ...)` and location-scoped incoming (R5), "NULL X = no cap" (R2), the fifth `unassigned` answer (R3 removes the missing-location case; a contact with no customer still gets its branch answer, only the send is skipped per R8), and a "Stock asks" card in place of a tab (R9).

## What exists today (measured 24 Sep 2026: main at 855ccf0c, #1118 head at c5249888)

### #1118, the path v2 changes (not on main)

- Quantity collection: `app/services/chatbot/turn/task.py` (`Slot` :34, `Task` :45, `StockQtyTask` :178, `TASK_KINDS = {"stock_qty": StockQtyTask(), "ideation": IdeationTask()}` :382, `tasks_after_reply` :773, which rebuilds the task from the stock tool's `stock_availability` block); `Focus.tasks: tuple[Task, ...]` on `turn/state.py:120`. The engine calls `turn_task.tasks_after_reply(...)` in `engine.py` (:2319 on the #1118 head). v2 does not touch any of this.
- The read: `GET /api/v1/inventory/stock/balance` (`app/api/v1/inventory/stock.py:203`) with `contact_id` + `space_id` (the contact the ask is on behalf of) and `requested_quantities` (JSON map, `parse_requested_quantities`). For a policy with `mode == "availability"` (UI label "Availability only", `services/stockVisibilityService.ts:114`; `stock_visibility_policies.mode` CHECK in `app/models/access.py:846`) `StockService._apply_stock_visibility` (`inventory_service.py:1246` on #1118) returns no rows and a `stock_availability` list, one entry per product code.
- Inside that block (#1118 `inventory_service.py:1458-1709`): `_supply_scope(column)` = `warehouse_criterion(policy, column)` + active warehouse + caller's `warehouse_ids` (:1482); open SO per product in that scope (:1497-1515); on hand minus open SO = `net_available` (:1665-1670). These two stay: they ARE R3 + R4.
- Also inside it, and removed by v2 (R5): the incoming read over `spo_allocations` (:1517-1566), the PO read over `purchase_order_lines` (:1568-1593), the threshold + lead-time read (:1595-1605), the `stock_verdict.verdict()` call and the `disclaimer` / `running_low` fields (:1680-1706). `app/services/stock_verdict.py` (pure, `Verdict(answer, running_low, sources, limited)`) has no other caller.
- Wording: MCP presenter `sorento_crm_mcp/sorento_crm_mcp/presenters.py` `_availability_line` (:1447 on #1118): "Yes, available." / "Yes, available, but running low." / "Not available, but there is ... incoming, ETA <date> ... purchase, ETA in <N> days." (:1454-1472). v2 replaces that function's body.
- #1118 also adds `system_settings.chatbot_stock_low_threshold_pct` (migration `dsv_0001`) and `StockLowThresholdCard.tsx` on Settings > Chatbot. After R6 nothing reads the threshold (no "running low" answer exists in B1 to B4).

### Incoming (main)

- `inbound_shipments` (`app/models/procurement.py:126`): `estimated_arrival_date Date` (:138), `shipment_status String(50)` (:143), `attachment_id` FK `attachments.id` (:150, the packing list), `eta_delay_date` (:177, NOT used, R5).
- `inbound_shipment_lines` (:343): `shipment_id` (:347), `product_id` (:348), `quantity_shipped` (:355), `quantity_received` (:408), `line_status` (:409).
- `app/services/incoming_stock_service.py`: `_still_incoming_filter()` (:73, `line_status NOT IN ('received')` AND `GREATEST(quantity_shipped - COALESCE(quantity_received,0), 0) > 0`) and `_not_draft_shipment_filter()` (:82, `shipment_status != _DRAFT_SHIPMENT_STATUS`) are exactly R5's line and shipment predicates; `_attachment_payload(attachment)` (:159) returns `{filename, file_path, mime_type}`.

### Contacts, customers, agents, messaging (main)

- `respond_contacts` (`app/models/access.py:230`): `chatbot_recall_enabled` (:266), `chatbot_stock_allowed` (:269). Surface: `PUT /api/v1/user-management/contacts/{id}/chatbot` (`ContactChatbotUpdate`, `app/api/v1/user_management/contacts.py:220`), manual dict builder `contact_to_response_dict` (`app/services/contact_service.py:317`), `turn_runtime._PROFILE_COLUMNS` (`turn_runtime.py:146`), FE `user-management/contacts/[id]/components/ContactChatbotSection.tsx` (Switch rows).
- `customers.sales_agent_id` FK `sales_agents.id` (`app/models/order.py:142`); settable from the CRM once #1177 merges. `sales_agents.contact_id` FK `respond_contacts.id` (`app/models/sales_agent.py:89`). Contact to customer: `contact_customer_service.resolve_customer(db, contact_id)` (`app/services/contact_customer_service.py:44`, `None` when unlinked or ambiguous).
- `send_text_or_template(...)` (`app/services/respond_messaging_service.py:545`), in-window text via `render_in_window_text` (:485), `TemplateSendSkipped` (:99). `integration_log` write pattern: `app/tasks/notification_tasks.py:178-231` (success and failure rows). Use cases: `TEMPLATE_DEFAULT_USE_CASES` (`app/models/respond_template.py:37`); FE labels `USE_CASES` (`services/whatsappTemplateService.ts:177`) read by `SetDefaultTemplateDialog.tsx`.
- Chatbot attachments: the engine emits a `send_attachments` action with `attachments_src` (`engine.py:3074`, `:3722`).

### Master data and RBAC (main)

- `_crud(module, resource, name_prefix)` (`app/rbac/permission_registry.py:11`) yields `.view/.add/.edit/.delete`; `_crud("master_data", "products", ...)` :193, `_crud("master_data", "product_categories", ...)` :205, `_crud("order_management", "customers", ...)` :98. Grant sweep precedent: `alembic/versions/522_autocount_pull_perms.py`.
- FE: `master-data-management/product-categories/components/CategoryForm.tsx` (modal), `master-data-management/products/components/ProductForm.tsx` (page, Basic Information card). `CustomerDetail.tsx` (`order-management/customers/components/`, 144 lines) is two Cards today, no tabs.

### Portal (main)

- `PriceTagRequestService.lookup_debtors_for_agent(db, contact_id)` (`app/services/price_tag_request_service.py:2367`): resolves the one `SalesAgent` whose `contact_id` is the portal contact (ordered, warns on two), then customers with `sales_agent_id == agent.id` (plus 24 months of order debtors). Route `GET /api/v1/public/portal/lookups/debtors-for-agent` (`app/api/v1/public/portal_price_tag.py:662`, `get_portal_token`).
- `app/(auth)/portal/components/PortalLanding.tsx` renders its list view with the repo `DataGrid` + `DataGridTable` (:1057-1074); `price_tag_request/page.tsx` is the per-type page shape.

## Journey (the UAC carries it in full)

A dealer contact on an "Availability only" policy names products; #1118's task collects a quantity per product. For each product the bot answers one of four fixed sentences and never a number of ours except Q and a date. For B1, B2, B4 the customer's sales agent gets one WhatsApp line when the contact's "Notify salesman" is on. Every answered ask is a row the office works on the customer's Asks tab and the agent works on the portal's Customer asks page.

## Slices

Every slice: migration, backend seam, frontend seam, tests (the `tester` agent writes them first, red, from this plan and the UAC; the `coder` makes them green), UAC ids. pytest on Postgres only (`tests/_pg_fixture.py`); CI has no data, every test seeds its own chain.

### S0 - Rebase and merge #1118

**Migration:** none new. `dsv_0001_chatbot_stock_low_threshold` re-parented onto main's head with `./scripts/alembic-reparent.sh`; `alembic heads` shows one.
**Backend / frontend seam:** none beyond conflict resolution. `git fetch origin main`, rebase or merge main into `feat/chatbot-dealer-stock-verdict`, resolve, CI green, merge.
**Tests:** #1118's own suites stay green on the rebased head (`tests/chatbot`, `tests/test_stock_availability_block.py`, `tests/test_stock_verdict.py`, MCP `tests/`). No new test.
**UAC:** AC-SA001, AC-SA002.
**Gate:** no v2 slice starts until #1118 is on main (R1).

### S1 - X and Y columns, permission, category and product forms

**Migration** `sa2_0001_xy_columns` (re-parented at PR time): `product_categories.chatbot_max_qty INTEGER NULL`, `product_categories.chatbot_eta_offset_days INTEGER NULL`, `products.chatbot_max_qty INTEGER NULL`, `products.chatbot_eta_offset_days INTEGER NULL`, CHECK `>= 0` on all four. No backfill: NULL is the shipped value and means 0 (R2: nothing answers until a category opts in). Inserts the four `_crud` slugs `master_data.chatbot_stock_limits.{view,add,edit,delete}` into `user_permissions` and grants `.view` + `.edit` to every role holding `master_data.products.edit` and to `admin`, integration roles excluded (the 522 shape).

**Permission:** `PERMISSION_REGISTRY.extend(_crud("master_data", "chatbot_stock_limits", "Chatbot Stock Limits"))` next to `product_categories` (R2: "from the _crud pattern"). Only `.view` (see the two values) and `.edit` (change them) are read by code; `.add` / `.delete` are the pattern's siblings and gate nothing (there is no row to add or delete).

**Resolution rule** (pure, `app/services/stock_ask_limits.py`, core): `effective(product, category) -> (max_qty: int, eta_offset_days: int)` = product value if not NULL, else the product's own category value if not NULL, else 0. No parent walk (R2).

**Backend seam:** the two fields on `ProductCategoryBase/Update/Response` and `ProductBase/Update/Response` (`app/schemas/product.py`), `>= 0` validated (422). The category PUT (`app/api/v1/master_data/categories.py`) and product PUT (`products.py`) raise `AppException(403)` when the body changes either field and the caller lacks `master_data.chatbot_stock_limits.edit`; the unchanged value passes so the ordinary form keeps saving. Responses always carry both fields: the values are not secret, and `.view` gates only whether the FE shows them (one rule, one place). Assert both fields in a response test (`response_model` drops undeclared fields).

**Frontend seam:** `CategoryForm.tsx` gains "Max quantity (assistant)" and "ETA offset (days)" number inputs, rendered when `useHasPermission("master_data.chatbot_stock_limits.view")`, disabled unless `.edit`. `ProductForm.tsx` Basic Information card gains the same two inputs beside the reorder fields, placeholder = the category value when the product value is empty. The product view renders the same card with the same fields in the same order (view = edit layout, R2); `-` when unset. No helper text.

**Tests (tester first):** `tests/test_stock_ask_limits.py`: `effective()` table (product set, category set, both, neither -> 0, zero is a value, parent category ignored). `tests/test_stock_ask_limits_api.py`: PUT category/product with `.edit` persists; without `.edit` and a changed value 403; without `.edit` and the unchanged value 200; negative 422; GET carries both fields; migration seeds the four slugs, sweeps `.view` + `.edit` onto a `master_data.products.edit` role and `admin`, not onto an `integration_*` role. Vitest: `CategoryForm` hides the fields without `.view`, disables without `.edit`; `ProductForm` shows the category placeholder.
**UAC:** AC-SA101 to AC-SA111.

### S2 - Contact toggles

**Migration** `sa2_0002_contact_toggles`: `respond_contacts.notify_salesman BOOLEAN NOT NULL DEFAULT false`, `respond_contacts.packing_list_allowed BOOLEAN NOT NULL DEFAULT false` (R7 names, R7 defaults).

**Backend seam:** `ContactChatbotUpdate` gains both as `bool | None` (absent = leave alone, the route's existing rule); `contact_to_response_dict` lists both; `turn_runtime._PROFILE_COLUMNS` selects both and `Profile` (`turn/state.py`) carries `notify_salesman: bool = False`, `packing_list_allowed: bool = False`, so S3/S4 read them off the profile the engine already loads.

**Frontend seam:** `ContactChatbotSection.tsx` gains two Switch rows, "Notify salesman" and "Packing list allowed"; `contactChatbotService.ts` + `useContactChatbot.ts` map and save them with the rest of the profile.

**Tests (tester first):** `tests/chatbot/test_stock_ask_contact_toggles.py`: PUT one toggle persists and returns it, the other untouched; GET lists both, default false; without `user_management.contacts.edit` 403; `load_profile` returns both (workspace row and NULL-workspace fallback), unknown contact false. Vitest: `ContactChatbotSection` renders both switches and saves the full profile.
**UAC:** AC-SA201 to AC-SA205.

### S3 - Four-branch verdict and the R5 ETA read

**Migration** `sa2_0003_drop_stock_low_threshold`: drops `system_settings.chatbot_stock_low_threshold_pct` (added by #1118's `dsv_0001`; after R6 nothing reads it). Removed from both manual `system_settings` dict builders and the Settings > Chatbot page (`StockLowThresholdCard.tsx` and its test deleted).

**Backend seam** (`StockService._apply_stock_visibility`, availability branch only; `detailed` / `compact` return earlier and are untouched, R10):
1. Keep: `_supply_scope`, the open SO read, `net_available` (R3, R4), `_resolve_ask`, the per-code merge, `needs_quantity` (so `StockQtyTask` keeps working unchanged, R1).
2. Delete: the `spo_allocations` read, the `purchase_order_lines` read, the threshold / lead-time read, the `verdict()` call, `stock_verdict.py`, `tests/test_stock_verdict.py`.
3. Add one read per page: X and Y via `stock_ask_limits.effective` for the page's products (products joined to their category, one query).
4. Add the R5 ETA read (one query per page, `app/services/incoming_stock_service.py` gains `earliest_packing_list_shipment(db, product_ids) -> {product_id: (shipment_id, estimated_arrival_date, attachment_id)}`): `inbound_shipments` join `inbound_shipment_lines` on `shipment_id`, `_not_draft_shipment_filter()`, `_still_incoming_filter()`, `inbound_shipments.attachment_id IS NOT NULL`, `line.product_id IN (...)`, ordered by `estimated_arrival_date ASC NULLS LAST`, first per product (`DISTINCT ON (product_id)`). No warehouse filter (ANY location, R5). No `eta_delay_date`.
5. Decision (pure, `app/services/stock_ask_branch.py`, replaces `stock_verdict.py`): `branch(q, x, available, shipment_date) -> "too_big" | "in_stock" | "incoming" | "no_incoming"`: `q > x` (x = 0 when unset, so every q >= 1 is `too_big`) -> `too_big`; `available >= q` -> `in_stock`; a shipment row exists -> `incoming`; else `no_incoming`. A shipment row whose `estimated_arrival_date` is NULL still counts as existing (nulls last); its entry carries no date and the presenter says "ETA to be confirmed" (the one case R5 leaves undated; flagged, not invented).
6. Entry shape (replaces `available` / `verdict` / `running_low` / `disclaimer`): `branch`, `cap_unset: bool` (X resolved from NULLs), `category_name` (for the B1 reason), `eta` (`dd/mm/yyyy` of `estimated_arrival_date + Y`, `incoming` only), `packing_list` (`_attachment_payload` of the shipment's attachment, `incoming` only AND only when the asking contact's `respond_contacts.packing_list_allowed` is true; the route already resolves that contact, so the raw GET never carries the file for a contact who may not have it). No quantity of ours on the wire.
7. Presenter `_availability_line` (MCP) renders R6 verbatim per entry, one line per product in asked order:
   - `too_big`: "The quantity is more than what I can confirm here, please refer to your salesman."
   - `in_stock`: "Yes, we have stock for <P> x <Q>, please refer to your salesman to proceed."
   - `incoming`: "No stock at the moment, ETA <dd/mm/yyyy>."
   - `no_incoming`: "No stock and no incoming at the moment, please refer to your salesman."
   `<P>` is `product_code` (fallback `product_name`, never the id).
8. Engine: at the `tasks_after_reply` call site, when an entry is `incoming` with `packing_list` present, emit a `send_attachments` action with that file (the existing action shape). Nothing else changes in the engine in S3.

**Frontend seam:** Settings > Chatbot loses the threshold card (only).

**Tests (tester first):** `tests/test_stock_ask_branch.py`: the UAC truth table. `tests/test_stock_availability_block.py` (rewritten where it pinned `verdict` / `disclaimer`, the old assertions deleted, not skipped): location scope (stock outside the policy set not counted); open SO subtracted; ETA picks the earliest `estimated_arrival_date` among shipments with a packing list; a shipment without `attachment_id` ignored even if earlier; draft shipment ignored; received line ignored; fully received quantity ignored; `eta_delay_date` ignored; a shipment into a warehouse outside the policy set still counts; `spo_allocations` and open PO lines produce no ETA; Y added across a month end; X unset -> `too_big` + `cap_unset`; product X overrides category X; `packing_list` present only with the toggle on; no digit of ours in any entry field; `detailed` and `compact` payloads byte-identical to before. MCP `tests/test_presenters_availability_lines.py` rewritten: four sentences, asked order, no UUID, no "running low", no "purchase". `tests/chatbot` engine test: B3 with toggle on emits `send_attachments`, off does not. The `demand_qty` / `stock_denied` suites untouched and green (R1). Migration test: the column is gone and `GET /system-settings` no longer lists it. Vitest: Settings > Chatbot page renders without the card.
**UAC:** AC-SA301 to AC-SA318.

### S4 - Agent notification + integration_log

**Migration:** none (use case registration is code; the template mapping is admin data).

**Backend seam:**
- `stock_ask_salesman` appended to `TEMPLATE_DEFAULT_USE_CASES` and to FE `USE_CASES` with a label.
- Engine, after the turn row is written (never before; the dealer's reply never waits on Respond), for each entry of the reply's `stock_availability` block with branch `too_big` / `in_stock` / `no_incoming`, when `Profile.notify_salesman` is true and the turn is live (not dry run, console or test): enqueue `app/tasks/stock_ask_tasks.notify_salesman(...)` on the `respond_io` queue with the ask facts. `incoming` never enqueues (R6 B3).
- Task: resolve customer (`resolve_customer`) -> `customers.sales_agent_id` -> `sales_agents.contact_id` -> `respond_contacts.respond_io_id`. A missing link is a skip with reason `no_customer` / `no_sales_agent` / `agent_has_no_contact` / `agent_contact_has_no_respond_id`, a warning log, no raise (R8).
- Context vars (one template, R8): `outcome` (phrase: `in stock` / `too big` / `no stock no incoming` / `no cap set for <category>` when `cap_unset`), `customer_name`, `contact_name` (the dealer contact who asked), `product` (code - name), `quantity`, `asked_at` (dd/mm/yyyy HH:MM, Malaysia wall clock). `send_text_or_template(db, identifier=respond_io_id, text=<default wording>, use_case="stock_ask_salesman", context_vars=..., respond_contact_id=agent_contact.id)`: template outside the window, in-window text following the template wording (R8, the function's own behaviour).
- One `integration_log` row per attempt, success or failure, the `notification_tasks.py:178-231` shape: `integration_channel="respond_io"`, `direction="outbound"`, `external_reference=respond_io_id`, `request_payload` = what was sent. In S4 alone `business_table="chatbot_turns"`, `business_id=turn_id`; S5 moves it to the ask row.

**Frontend seam:** the use case label in the Set Default Template dialog only.

**Tests (tester first):** `tests/chatbot/test_stock_ask_notify.py` (`send_text_or_template` monkeypatched): toggle on + B1 / B2 / B4 enqueue one job each; B3 none; toggle off none; dry run / console none; job only after the turn row is written; outcome phrase per branch and `no cap set for <category>` when `cap_unset`; each missing link a skip with its reason and no send; window open `sent_as == "text"`, closed with a mapped template `sent_as == "template"`, closed and unmapped `TemplateSendSkipped` -> failed log row; Respond 401 -> failed row with status and body; every attempt exactly one `integration_log` row. `tests/test_respond_template_use_cases.py` extended: `set_default` accepts `stock_ask_salesman`. Vitest: the dialog lists the label.
**Depends on:** #1177 merged.
**UAC:** AC-SA401 to AC-SA410.

### S5 - Asks table + CRM Asks tab

**Migration** `sa2_0004_stock_asks`:

```
stock_asks
  id                  uuid PK
  company_id          uuid FK companies.id            (CompanyScopedMixin, from the customer)
  customer_id         uuid NULL FK customers.id ON DELETE CASCADE
  contact_id          text FK respond_contacts.id ON DELETE SET NULL
  product_id          uuid FK products.id ON DELETE SET NULL
  product_code        varchar(100) NOT NULL               (snapshot)
  quantity            integer NOT NULL
  branch              varchar(20) NOT NULL CHECK in (too_big, in_stock, incoming, no_incoming)
  answer_summary      text NOT NULL                       (the line the dealer was sent)
  notified_agent      boolean NOT NULL DEFAULT false
  notify_skip_reason  varchar(80) NULL                    (why not, when not)
  state               varchar(10) NOT NULL DEFAULT 'open' CHECK in (open, done)
  note                text NULL
  created_at / updated_at
  index (customer_id, created_at desc)
```

Exactly R9's fields. `customer_id` nullable: an ask from a contact with no resolvable customer is still recorded (R8 "record the ask"); such a row shows on no customer tab and no portal page (nothing to hang it on) and is visible in the DB only; flagged in the UAC. No `sales_agent_id` snapshot (the portal scope reads the customer's current agent, R9). No opportunity column (R9: #1170).

**Backend seam:**
- Engine: at the same post-turn point as S4, one row per entry with a branch (all four), live turns only; `notified_agent=false` + `notify_skip_reason` (`toggle_off` / `not_notified_branch` for B3) at write; the S4 task flips `notified_agent=true` on success or sets its skip / failure reason. `integration_log.business_table="stock_asks"`, `business_id=ask.id`.
- `GET /api/v1/order-management/customers/{id}/asks` (paged, newest first, `buildDataGridParams` contract, `list_query_registry` entry for column config; gated by `order_management.customers.view`) and `PATCH /api/v1/order-management/customers/{id}/asks/{ask_id}` `{state, note}` (gated by `order_management.customers.edit`, R9). Rows carry `contact_name`, `product_code`, never a bare id. Service `app/services/stock_ask_service.py` (core).

**Frontend seam:** `CustomerDetail.tsx` gains line tabs "Details" (the two existing cards, unchanged) and "Asks". Asks tab: DataGrid (`tableLayout: { width: 'fixed', columnsResizable: true }`, `columnResizeMode: 'onChange'`, explicit sizes, truncate + title): Asked at, Contact, Product, Qty, Branch (Badge), Answer, Notified (Badge + reason in `title`), State, Note. State is a required `SearchableSelect` (open / done; required, so not clearable) and Note an inline text input, editable when the user holds `order_management.customers.edit`, read-only values otherwise (view = edit layout). Empty state names what fills it. Service `services/stockAskService.ts` -> hooks `useCustomerAsksQuery` / `useUpdateAskMutation` (invalidate + toast, `extractApiError`).

**Tests (tester first):** `tests/chatbot/test_stock_ask_record.py`: one row per product per live turn with the right branch, quantity, answer summary; none on dry run / console; B3 `notify_skip_reason = not_notified_branch`; toggle off `toggle_off`; S4 success flips `notified_agent`; skip reason written on each missing link; unresolved customer -> row with NULL `customer_id`; integration_log references the ask. `tests/test_stock_asks_api.py`: GET newest first, names not ids, company scope (another company's user sees none), 403 without `.view`; PATCH state + note persists, `done -> open` allowed, 403 without `.edit`, ask of another customer 404; `test_schema_uuid_id_principle.py` passes. Vitest: Asks tab renders grid + empty state; read-only without `.edit`; state change calls the mutation.
**UAC:** AC-SA501 to AC-SA512.

### S6 - Portal "Customer asks" page (last)

**Migration:** none.

**Backend seam:** extract the agent resolution at the top of `PriceTagRequestService.lookup_debtors_for_agent` (the ordered `SalesAgent.contact_id == contact_id` query + two-link warning) into `sales_agent_for_contact(db, contact_id) -> SalesAgent | None` and call it from both places (reuse, not a copy). New `app/api/v1/public/portal_customer_asks.py` mounted under `/portal` like `portal_price_tag`: `GET /api/v1/public/portal/customer-asks` (paged, `q` on customer / product) and `PATCH /api/v1/public/portal/customer-asks/{ask_id}` `{state, note}`, both on `get_portal_token`. Scope: asks whose `customers.sales_agent_id == sales_agent_for_contact(token.contact_id).id` (customers assigned to that agent only, R9; not the 24-month order debtors). No linked agent -> 403 `NOT_A_SALES_AGENT`; an ask outside the scope -> 404.

**Frontend seam:** `app/(auth)/portal/customer_asks/page.tsx` rendering `CustomerAsksList` in `app/(auth)/portal/components/`, the same `DataGrid` + `DataGridTable` list pattern as `PortalLanding`'s list view: Asked at, Customer, Contact, Product, Qty, Branch, Answer, Notified, State (editable), Note (editable). Portal nav entry "Customer asks" shown only when the contact is a linked agent (the GET's 403 hides it). Usable at 375px.

**Tests (tester first):** `tests/test_portal_customer_asks.py`: agent contact sees asks of customers assigned to their agent only; another agent's customer's ask not listed and PATCH 404; non-agent contact 403; PATCH state + note persists; `lookup_debtors_for_agent` suite still green after the extraction. Vitest: `CustomerAsksList` renders grid, empty state, edits state + note.
**UAC:** AC-SA601 to AC-SA607.

## Simplest thing, not built

- No customer stock location column (R3). No parent-category walk for X / Y (R2; trigger: a category whose X the owner wants inherited). No per-company X / Y.
- No `TaskKind` or task change: #1118's collection is reused as is (R1).
- No new use case per branch: one template, one outcome slot (R8). No digest, no retry beyond the existing `respond_io` log sweeper, no in-app notification.
- No follow-up states beyond open / done, no assignment, no SLA, no export, no archive; no opportunity link (R9, #1170).
- No new portal visibility form type: the page's gate is "this contact is a linked sales agent", the same resolution the debtor lookup uses.

## Risks and rebase points

- #1118 is +18k lines and 44 commits; S0 may take a round of conflict work in `engine.py` and `turn_runtime.py`. Line numbers above cite #1118's head and will move.
- `dsv_0001` adds the threshold column that S3 drops. If the owner prefers, S0 can instead drop `dsv_0001` and the card before #1118 merges; the plan keeps S0 a pure rebase so #1118 lands as reviewed.
- #1177 not merged blocks S4 onwards (the agent link is settable only through it).
- A shipment with a packing list but NULL `estimated_arrival_date` is `incoming` with no date; the plan answers "ETA to be confirmed" and the UAC pins it (AC-SA309). Owner may re-rule.
- Security review joins S3 (per-contact attachment release), S4 (outbound send) and S6 (portal scope).

## Files (expected)

Backend: `alembic/versions/sa2_000{1..4}_*.py`, `app/models/product.py`, `app/models/access.py`, `app/models/user.py`, `app/models/stock_ask.py` (new), `app/models/respond_template.py`, `app/schemas/product.py`, `app/schemas/stock_ask.py` (new), `app/rbac/permission_registry.py`, `app/api/v1/master_data/categories.py`, `app/api/v1/master_data/products.py`, `app/api/v1/user_management/contacts.py`, `app/api/v1/user_management/settings.py`, `app/api/v1/order_management/customers.py`, `app/api/v1/public/portal_customer_asks.py` (new), `app/api/v1/public/__init__.py`, `app/services/stock_ask_limits.py` (new), `app/services/stock_ask_branch.py` (new), `app/services/stock_verdict.py` (deleted), `app/services/inventory_service.py`, `app/services/incoming_stock_service.py`, `app/services/stock_ask_service.py` (new), `app/services/price_tag_request_service.py`, `app/services/contact_service.py`, `app/services/list_query_registry.py`, `app/services/chatbot/engine.py`, `app/services/chatbot/turn_runtime.py`, `app/services/chatbot/turn/state.py`, `app/tasks/stock_ask_tasks.py` (new).
MCP: `sorento_crm_mcp/sorento_crm_mcp/presenters.py`.
Frontend: `product-categories/components/CategoryForm.tsx`, `products/components/ProductForm.tsx` (+ product view), `user-management/contacts/[id]/components/ContactChatbotSection.tsx` + service + hook, `user-management/settings/chatbot/` (card removed), `order-management/customers/components/CustomerDetail.tsx` + new `CustomerAsksTab.tsx`, `services/stockAskService.ts`, `services/whatsappTemplateService.ts`, `app/(auth)/portal/customer_asks/page.tsx`, `app/(auth)/portal/components/CustomerAsksList.tsx`.
