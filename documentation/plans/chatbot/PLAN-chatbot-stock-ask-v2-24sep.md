# PLAN - Chatbot stock ask v2: X quantity threshold, Y ETA offset, per-contact toggles, salesman notification, asks record

Status: DRAFT, pre-grill (24 Sep 2026). Track: full feature (two migrations, one new permission slug, one new table). Nothing built.
Issue: #1168 (owner brief + five rulings, 24 Sep 2026). Model map on #1170 (comment of 24 Sep).
UAC: `chatbot-stock-ask-v2-24sep-acceptance-criteria.md`
Classification: the X / Y columns, the contact toggles and the asks table are CORE in `public` (they extend `product_categories`, `products`, `respond_contacts`, `customers`); the decision and the notification live inside the `chatbot` MODULE package (`app/services/chatbot/`), same boundary rule as every other lane there.
Depends on: PR #1177 (#1170 slice 1, branch `feat/customer-sales-agent-assignment`, open) for `customer.sales_agent_id` being settable and visible from the CRM. The column and FK already exist on `customers` (`app/models/order.py:142-146`); #1177 adds the schema fields, the select route and the form field. S3 to S5 need it merged; S1 and S2 do not.

## Owner rulings (verbatim intent, #1168 comment of 24 Sep)

1. X (max quantity the AI answers for) and Y (days added to ETA) are plain columns on `product_categories` and `products`; product overrides category when set. Editing them is an RBAC permission, not a fixed role.
2. "Stock covers Q" checks the customer's assigned location only, not company-wide on hand.
3. No stock + an ETA exists: the answer is always system ETA + Y. No "no ETA" fallback.
4. Salesman notification: Respond template defaults outside the 24h window; inside the window, plain text with the same wording. That is what `send_text_or_template` already does.
5. The traceability record is not a plain log: it is a salesperson sales-management function (what each customer asked, when, what the bot answered, follow-up state). Designed with #1170, seeded by #1168 events. Grill the shape before building.

## What exists today (measured on main at 028083e2, 24 Sep 2026)

### The stock-denial branch this plan replaces

- Route (`app/services/chatbot/engine.py:1870-1875`): after the access check, `stock_denial_enabled and _stock_check_denied(db, envelope, verdict)` routes to `demand_qty` when `_demand_qty_missing(verdict)` else `stock_denied`; otherwise `turn_route(plan)`.
- `_stock_check_denied` (`engine.py:3247-3264`): `profile.stock_allowed is not True and verdict.intent_hint == "check_stock" and entities non-empty`. `profile.stock_allowed` is `respond_contacts.chatbot_stock_allowed` (default ON, `app/models/access.py:269`) read by `turn_runtime.load_profile` (`turn_runtime.py:146-149, 306`).
- `_demand_qty_missing` (`engine.py:3267-3269`): `demand_qty` empty or 0. The `demand_qty` lane answers with copy key `demand_qty` = "Please specify your demand quantity" (`app/services/chatbot_reply_copy.py:24, 142-146`; rendered in `tail/outcome.py:159-160`). So on main the quantity IS collected before any answer on this path. The brief's "stop asking dealer" PR could not be found by that title; the nearest open PR is #1118 (dealer stock verdict, see risks).
- Global switch: `system_settings.chatbot_stock_denial_enabled`, default false (`app/models/user.py:580`, read in `engine.py:3947-3959`). With it off no turn reaches `stock_denied` or `demand_qty`.
- The `stock_denied` answer today (`engine.py:2556-2562`): `canned_lanes.stock_denied_text` renders the `access_denied` copy with subject "stock" (`lanes/canned.py:83-95`), i.e. a refusal. The business lane stamps `not_allowed_check_stock` (`engine.py:3803`, `lanes/business/__init__.py:618`) and `answer.validator` (`lanes/business/answer.py:122-179`) sums `stock_qty` over every row the visibility policy returned and prints "Quantity of Q for product P can be fulfilled." or "... cannot be fulfilled. Total available quantity is N." That second sentence prints our number, which ruling-style item 1 of the brief forbids ("never reveal stock").
- Contact-side surface: `PUT /api/v1/user-management/contacts/{id}/chatbot` (`app/api/v1/user_management/contacts.py:220-268`, `ContactChatbotUpdate`, gated by `user_management.contacts.edit`), the manual dict builder `contact_service.py:347`, FE `ContactChatbotSection.tsx` ("Stock checks" switch) + `contactChatbotService.ts` + `useContactChatbot.ts` under `user-management/contacts/[id]/`.

### The recipient chain for the notification

- `customers.sales_agent_id` FK `sales_agents.id` (`app/models/order.py:142-146`). Set from the CRM only once #1177 merges.
- `sales_agents.contact_id` Text FK `respond_contacts.id` (`app/models/sales_agent.py:89-93`), eager `contact` relationship and `contact_name` property (`:103-116`).
- `respond_contacts.respond_io_id` is the identifier every CRM send uses (`app/tasks/notification_tasks.py:154, 165`).
- Contact to customer: `respond_contact_customers` link table (`app/models/access.py:11-60`), resolved by `contact_customer_service.resolve_customer(db, contact_id)` (one link, or the primary; `None` when unlinked or ambiguous).
- `send_text_or_template(db, identifier=, text=, use_case=, context_vars=, respond_contact_id=)` (`app/services/respond_messaging_service.py:545-660`): window open sends text rendered through `render_in_window_text` (`:485-542`, the use case's default template body, so in-window and out-of-window read the same); window closed sends the use case's default template. Returns `{sent_as, response, window_state, request_payload, rendered_text?}`. Raises on Respond errors. The caller writes the `integration_log` row: pattern at `notification_tasks.py:159-191` (`IntegrationLogService.create_integration_log(IntegrationLogCreate(integration_channel="respond_io", business_table=, business_id=<uuid>, external_reference=identifier, direction="outbound", endpoint=, http_method="POST", status=), request_payload_dict=)`), success and failure both logged.
- A use case must be listed in `TEMPLATE_DEFAULT_USE_CASES` (`app/models/respond_template.py:37-120`) before an admin can map a template to it on Integration > WhatsApp templates (`SetDefaultTemplateDialog.tsx` reads a `USE_CASES` label list).

### Master data

- `product_categories` (`app/models/product.py:32-75`): company-scoped, `parent_category_id`, `display_order Integer`. `products` (`:165-280`): `category_id` NOT NULL, `reorder_level Integer`, `reorder_quantity Integer`, `warranty_months Integer`.
- Schemas `app/schemas/product.py`: `ProductCategoryBase/Create/Update/Response` (:9-34), `ProductBase` (:125), `ProductUpdate` (:206), `ProductResponse` (:351).
- Routes: `app/api/v1/master_data/categories.py` POST `.add` (:146), PUT `.edit` (:164), DELETE `.delete` (:181). Products the same shape in `products.py`.
- Permissions: `app/rbac/permission_registry.py` `_crud(module, resource, name_prefix)` (:11) yields view/add/edit/delete; `_crud("master_data", "product_categories", ...)` at :205; single-slug appends at :194-199 (`master_data.products.import` etc.). Grant-sweep precedent: `alembic/versions/522_autocount_pull_perms.py` (insert slug, sweep onto every role holding a sibling slug, grant `admin`, integration roles excluded).
- FE: `CategoryForm.tsx` is a Dialog (modal) with category_code, category_name, description, display_order, is_active, is_searchable. `ProductForm.tsx` is a dedicated page with tabs basic / pricing / specifications / suppliers / attachments; `warranty_months` and the reorder fields sit in the Basic Information card (:783-801). `ProductDetail.tsx` is the view. Permission check hook: `useHasPermission(slug)` (`hooks/usePermissions.ts`).

### Stock and incoming

- `stock` is one row per (product, warehouse) with `quantity_on_hand`, `quantity_reserved`, computed `quantity_available` (`app/models/inventory.py:115-161`). `warehouses` carries `warehouse_code`, `pool_warehouse_id`, `segment` (dealer / project), `counts_as_available`, `fulfilment_planning` (`:26-91`).
- Incoming: `inbound_shipments.estimated_arrival_date` (first published) and `eta_delay_date` (the revised, accurate one; `app/models/procurement.py:175-177`); "still incoming" is `inbound_shipment_lines` with remaining > 0, read by `IncomingStockService.incoming_for_product` (`app/services/incoming_stock_service.py:253`), which also exposes the shipment's packing-list attachment (`attachment_id`, filename / path). `spo_allocations.expected_date` (`procurement.py:513`) is the per-line promised arrival that #1118 uses for its ETA.

### The customer's assigned location: none exists

Checked every candidate:

- `customers` (`app/models/order.py:94-146`): no warehouse, location, branch or region-to-warehouse column. `region` is AutoCount `AreaCode` free text, not a stock location.
- `sales_agents.location_group` (`sales_agent.py:79-85`): a `String(16)` OWNERSHIP GROUP code (`BB` for the BRW-BB / MWH-BB / DC1-BB bins), NULL on all 38 codes as shipped, and the Warehouse model forbids parsing warehouse codes at runtime (`pool_warehouse_id` is "STORED, never parsed"). Not a location and not populated.
- `stock_visibility_policies` (`access.py:775-870`): a warehouse SET per contact / access type / global for what the bot may show. Per contact, not per customer, and #1118 already uses it for a different answer.
- `warehouses.segment` (dealer / project): a property of the bin, not of the customer.

**Smallest addition (S3 migration):** `customers.stock_warehouse_id UUID NULL, FK warehouses.id ON DELETE SET NULL`, index on it. Edited on `CustomerForm.tsx` as a clearable `SearchableSelect` "Stock location" next to the Sales agent field #1177 adds; shown as a read-only value in the Contact Information section of `CustomerDetail.tsx`; carried on `CustomerCreate/Update/Response` as `stock_warehouse_id` + `stock_warehouse_code` (no UUIDs on screen). No backfill: NULL is the honest value for every existing row (the trigger for a backfill is a rule from the owner mapping customers to bins; none exists). Bulk assignment stays out (see "Simplest thing", S3) and is a grill question.

## Journey (the UAC carries the full seven steps)

Actor: a dealer contact on WhatsApp whose customer record has a sales agent and a stock location. They name a product and (if not already) a quantity. The bot answers one of four fixed sentences and never a number of ours. Their salesman gets one WhatsApp line per notified ask, and the office sees every ask on the customer's page with a follow-up state.

## Design, sliced

Each slice: migration, backend seam, frontend seam, tests (pytest per slice; the live console check only at the end of S5), dependencies, and what was deliberately not built.

### S1 - X and Y on categories and products, product override, permission-gated edit

**Migration** `<n>_stock_ask_xy_columns` (re-parented onto main's head at PR time with `./scripts/alembic-reparent.sh`; main's newest numbered revision is `526_chatbot_media_attach_type`, followed by the `bftp_0001` / `oirs_*` chain): `product_categories.chatbot_max_qty INTEGER NULL`, `product_categories.chatbot_eta_offset_days INTEGER NULL`, `products.chatbot_max_qty INTEGER NULL`, `products.chatbot_eta_offset_days INTEGER NULL`, CHECK `>= 0` on all four. Same migration inserts the permission `master_data.products.chatbot_stock_rules` (`_crud` is not used for the slug itself, because there is no view/add/delete: it is one `edit`-shaped capability. It IS appended via the registry's single-slug pattern at `permission_registry.py:194-199`, next to `.import` / `.export`) and sweeps it onto every role holding `master_data.products.edit`, integration roles excluded, `admin` granted explicitly (the 522 shape). No data backfill: NULL is the shipped value (see resolution below).

**Resolution rule** (one pure function, `app/services/stock_ask_rules.py`, core, no chatbot import): `effective(product) -> (max_qty, eta_offset_days)` = product value when not NULL else the product's own category's value else NULL. The parent-category tree is NOT walked (see "not built"). Semantics of NULL are a grill question (G3); the plan's recommendation: NULL `max_qty` = no cap, NULL `eta_offset_days` = 0.

**Backend seam:** the four fields on `ProductCategoryBase/Update/Response` and `ProductBase/Update/Response`; `ProductResponse` additionally carries `chatbot_max_qty_effective` and `chatbot_eta_offset_days_effective` so the product page can show the inherited value next to the override. The category PUT and product PUT routes reject (403, `AppException`) a body that CHANGES either field when the caller lacks `master_data.products.chatbot_stock_rules`; a body carrying the unchanged current value passes (so the ordinary edit form keeps working for editors without the grant). Assert the response fields in a test (`response_model` drops undeclared fields silently, LESSONS).

**Frontend seam:** `CategoryForm.tsx` gains "Max quantity the assistant answers" and "ETA offset (days)" number inputs in the same modal, read-only (value shown, input disabled) when `useHasPermission("master_data.products.chatbot_stock_rules")` is false. `ProductForm.tsx` Basic Information card gains the same two inputs beside the reorder fields with the inherited category value shown as the placeholder when the product value is empty; `ProductDetail.tsx` shows the two facts in the same section, in the same order (view = edit layout). Category detail page (`product-categories/[id]`) shows the two facts. `-` when unknown (ADR 1e). No helper text explaining the feature (cursor rule).

**Tests (pytest, `tests/test_stock_ask_rules.py`, `tests/test_product_category_stock_rules_api.py`):**
- `effective()` truth table: product set / category set / both / neither, zero is a value not NULL.
- PUT category with the grant changes X and Y; PUT without the grant and a changed X is 403; PUT without the grant and the unchanged X is 200.
- Same three for PUT product.
- GET product carries the four raw fields plus the two effective fields; GET category carries its two.
- Migration: permission row exists after upgrade; a role holding `master_data.products.edit` holds the new slug; an `integration_*` role does not.
- Vitest: `CategoryForm` renders the two fields disabled without the grant; `ProductForm` shows the inherited placeholder.

**Depends on:** nothing.

**Simplest thing, not built:** no `scm.reorder_policy`-style scope table (the owner ruled plain columns; the #1170 comment names that precedent, and the second numeric per-category setting is the trigger to revisit). No parent-category walk (trigger: the first category whose X lives on its parent). No dedicated permission page: the slug rides the existing role permission editor. No per-company override.

### S2 - per-contact toggles: notify salesman, packing list allowed

**Migration** `<n>_contact_stock_ask_toggles`: `respond_contacts.chatbot_notify_salesman BOOLEAN NOT NULL DEFAULT false`, `respond_contacts.chatbot_packing_list_allowed BOOLEAN NOT NULL DEFAULT false`. Prefixed `chatbot_` to sit with `chatbot_stock_allowed` / `chatbot_recall_enabled` (the brief's short names `notify_salesman` / `packing_list_allowed` are these two). Default OFF for both: a notification is outbound traffic to a salesman and the packing list reveals quantities, so neither may switch on by migration.

**Backend seam:** `ContactChatbotUpdate` gains both as `bool | None` ("absent = leave alone", the route's existing rule, `contacts.py:230-233, 256-261`); `contact_to_response_dict` (`contact_service.py:347`) lists both; `turn_runtime._PROFILE_COLUMNS` (`turn_runtime.py:146`) selects both and `Profile` (`turn/state.py:128`) carries `notify_salesman: bool = False`, `packing_list_allowed: bool = False`, so S3 and S4 read them off the profile the engine already loads (one query, not a second).

**Frontend seam:** `ContactChatbotSection.tsx` gains two switches under "Stock checks": "Notify salesman on stock asks" and "Packing list may be sent"; `contactChatbotService.ts` maps them (`notify_salesman`, `packing_list_allowed`) and sends them on save with the rest of the profile.

**Tests (pytest, `tests/chatbot/test_stock_ask_contact_toggles.py`, shape of `test_rearch_s6_stock_allowed.py`):**
- PUT `/contacts/{id}/chatbot` with `chatbot_notify_salesman: true` persists and is returned; absent leaves the other toggle untouched.
- GET contact carries both keys (dict builder), default false.
- `load_profile` returns both flags; a NULL-workspace fallback row returns them too.
- Vitest: `ContactChatbotSection` renders both switches and saves the full profile on toggle.

**Depends on:** nothing.

**Simplest thing, not built:** no per-access-type tier for these toggles (the `stock_visibility_policies` three-tier shape exists for a different question; two booleans on the contact is the owner's ask). No bulk flip script; `scripts/set_contact_outbound.py` is the shape if a roll-out needs one.

### S3 - the four-branch decision in place of `stock_denied`

**Migration** `<n>_customer_stock_warehouse`: `customers.stock_warehouse_id UUID NULL FK warehouses.id ON DELETE SET NULL` + index (see "The customer's assigned location" above).

**Gate (unchanged):** the same predicate that routes to `stock_denied` today (`engine.py:1872`, global `chatbot_stock_denial_enabled` on + contact `chatbot_stock_allowed` off + `check_stock` with entities). The `demand_qty` half stays exactly as is: no quantity, ask for one. Grill question G2 confirms this gate and the label of the contact switch.

**Facts read once per turn** (`app/services/chatbot/lanes/stock_ask.py`, new, module-private):
1. Customer: `contact_customer_service.resolve_customer(db, contact_row_id)` (the contact's CRM row id, resolved the way `load_profile` resolves the profile, workspace-scoped). None means "no customer".
2. Location: `customers.stock_warehouse_id`. NULL means "no location".
3. Product(s): the resolved product entities on the turn (`verdict.entities` with `product_id`), one decision per product; Q = `verdict.demand_qty` (one scalar per turn on main).
4. X, Y: `stock_ask_rules.effective(product)`.
5. On hand available at the location: `stock.quantity_available` for (product, location), 0 when no row.
6. System ETA: the earliest still-incoming shipment carrying the product INTO the customer's location, date = `COALESCE(eta_delay_date, estimated_arrival_date)` on `inbound_shipments`, via `IncomingStockService.incoming_for_product` filtered to that warehouse. None when no such shipment or no dated one. Grill question G4 fixes the date source and the location scope of incoming.

**Decision** (pure, `decide(q, x, available, eta, y) -> Decision(kind, eta_told)`), in this order:
1. `x is not None and q > x` -> `too_big`.
2. `available >= q` -> `in_stock`.
3. `eta is not None` -> `incoming`, `eta_told = eta + y days`.
4. else -> `no_incoming`.

No customer, or no location: the decision cannot be made. The reply is the `too_big` sentence's sibling "please refer to your salesman" WITHOUT the "too big" clause (a fifth copy key `stock_ask_unassigned`), and the S4 notification reason is `no_location` / `no_customer`. Recommended in G1; the alternative (fall back to the visibility policy's warehouse set) is what #1118 does and is named there for the owner to choose.

**Answers as copy keys** (the customer's reply is composed by the engine and handed back as the turn's `send_message` action, the same tail every answer takes; it is in-window by construction because the customer just wrote). Registered in `CHATBOT_REPLY_COPY` (`chatbot_reply_copy.py:126`) so the owner can reword them on Settings > AI Prompts like every other canned line, with these defaults:

| key | default text | tokens |
|---|---|---|
| `stock_ask_too_big` | "Thank you for your enquiry. For a quantity of {{quantity}} of {{product}}, please refer to your salesman, who will confirm availability and pricing for you." | quantity, product |
| `stock_ask_in_stock` | "Yes, {{product}} is in stock. Please refer to your salesman to place the order." | product |
| `stock_ask_incoming` | "{{product}} is not in stock at the moment. The next arrival is expected on {{eta}}." | product, eta (dd/mm/yyyy, Malaysia wall clock) |
| `stock_ask_no_incoming` | "{{product}} is not in stock at the moment and there is no incoming shipment scheduled. Please refer to your salesman." | product |
| `stock_ask_unassigned` | "Thank you for your enquiry about {{product}}. Please refer to your salesman, who will confirm availability for you." | product |

Multi-product turns: one line per product, joined by newlines, in the order the entities were named. The `answer.validator` sentence that prints "Total available quantity is N" is deleted on this arm (it can no longer be reached: the arm no longer calls the fetch; `not_allowed_check_stock` stamping is retired with it).

**Packing list on branch 3:** the reply is the date only. When `Profile.packing_list_allowed` is true the turn's actions also carry the shipment's packing-list attachment (the `attachment_id` `incoming_for_product` already exposes) the same way an incoming answer attaches it today; when false, no attachment and no quantity. Grill question G8 confirms this is the whole meaning of toggle (b).

**Frontend seam:** `CustomerForm.tsx` "Stock location" clearable `SearchableSelect` over active warehouses (code - name, existing warehouse select service if one exists, else a `warehouses-select` sibling of the `sales-agents-select` route #1177 adds); `CustomerDetail.tsx` Contact Information shows "Stock location" as code - name or `-`; customers list column optional (not added).

**Tests (pytest, `tests/chatbot/test_stock_ask_decision.py`, `tests/chatbot/test_stock_ask_engine.py` on `tests/chatbot/conftest.py::session_factory` + `set_chatbot_switches`, `tests/test_customer_stock_warehouse.py`):**
- `decide()` truth table: Q > X; Q == X with stock; stock exactly Q; stock Q-1 with ETA; stock Q-1 without ETA; X NULL with huge Q; Y 0; Y 7 across a month end.
- Location scope: stock at another warehouse does not count (available 0 at the assigned bin, 500 elsewhere -> not `in_stock`).
- Incoming scope: a shipment into another warehouse does not produce an ETA (per G4's answer; the test is written both ways and one is kept).
- ETA date source: `eta_delay_date` wins over `estimated_arrival_date`; a shipment with neither is not an ETA.
- Engine end to end: each of the four branches yields its sentence and no digits of ours appear in the reply except Q and the date (regex guard); the `demand_qty` ask still fires with no quantity; a contact with stock allowed never enters the arm; switch off never enters the arm; no customer / no location yields `stock_ask_unassigned`.
- Multi-product turn yields one line per product.
- Packing list: toggle on attaches, toggle off does not.
- Customer API: `stock_warehouse_id` persists, unknown id 422, inactive warehouse 422, cleared to NULL, response carries `stock_warehouse_code`.
- Copy keys: registered, seeded, tokens declared (the registry's own consistency test).
- Vitest: `CustomerForm` renders the clearable select; `CustomerDetail` shows `-` when unset.

**Depends on:** S1, S2, PR #1177 merged (the form field sits beside its Sales agent field and the customer response shape it adds).

**Simplest thing, not built:** no per-product quantity capture (main's `demand_qty` is one scalar per turn; #1118's `Focus.tasks` is the richer shape and is not duplicated here; if #1118 merges first, S3 reads `entities[].quantity` instead, one seam). No threshold above which the ETA is withheld (ruling 3). No pool / borrow ladder: the assigned bin only (ruling 2). No bulk location assignment (grill G1; the customer import is the existing bulk path if the owner wants a column there). No new lane kind: `stock_denied` keeps its `branch_kind` so traces, `trace.py:250` labels and the console stay valid.

### S4 - salesman notification through `send_text_or_template`, logged

**Migration:** none (use case registration is code; the template mapping is data an admin sets).

**Use case:** `stock_ask_salesman` appended to `TEMPLATE_DEFAULT_USE_CASES` (`respond_template.py:37-120`) and to the FE `USE_CASES` label list the Set Default Template dialog reads. ONE use case with an outcome phrase, not three templates (grill G5). Context vars: `contact_name` (the salesman, the recipient's name), `customer_name`, `product` (code - name), `quantity`, `outcome`, `message` (the full text, so an unmapped in-window send still reads right). Default text, which is also the in-window text when no template is mapped:

| decision | `outcome` | `message` |
|---|---|---|
| `too_big` | "quantity too large for the assistant to answer" | "Customer {{customer_name}} asked about {{product}}, quantity {{quantity}}: quantity too large for the assistant to answer. Please follow up." |
| `in_stock` | "in stock" | "Customer {{customer_name}} asked about {{product}}, quantity {{quantity}}: in stock. Please follow up." |
| `no_incoming` | "no stock and no incoming" | "Customer {{customer_name}} asked about {{product}}, quantity {{quantity}}: no stock and no incoming shipment. Please follow up." |
| `unassigned` | "assistant could not answer (no stock location on the customer)" | same shape |

Branch 3 (`incoming`) sends no notification (the brief lists notifications for 1, 2 and 4 only; G5 confirms).

**Backend seam:** after the reply is composed and the turn is written (never before: the customer's answer must not wait on Respond), the engine enqueues `app/tasks/stock_ask_tasks.notify_salesman(turn_id, product_id, decision, ...)` on the existing `respond_io` RQ queue (Respond sends run only on the worker, CLAUDE.md), skipped on `dry_run` and on console / test turns, and only when `Profile.notify_salesman` is true. The task resolves the recipient: customer -> `sales_agent_id` -> `sales_agents.contact_id` -> `respond_contacts.respond_io_id`; any missing link is a recorded skip (`no_customer`, `no_sales_agent`, `agent_has_no_contact`, `contact_has_no_respond_id`), a warning log, and no raise. It calls `send_text_or_template(db, identifier=respond_io_id, text=message, use_case="stock_ask_salesman", context_vars=..., respond_contact_id=contact.id)` and writes ONE `integration_log` row per attempt, success or failure, `integration_channel="respond_io"`, `business_table="chatbot_turns"`, `business_id=turn_id`, `external_reference=respond_io_id`, `direction="outbound"`, `endpoint="https://api.respond.io/v2/contact/id:<respond_io_id>/message"`, `request_payload` = what was actually sent (text or template), exactly the `notification_tasks.py:159-231` shape. S5 moves `business_table` / `business_id` to the ask row.

**Frontend seam:** none beyond the use case label. The row shows up in the existing Respond outbox view of `integration_log`.

**Tests (pytest, `tests/chatbot/test_stock_ask_notify.py`, `send_text_or_template` and `RespondClient` monkeypatched; `tests/test_respond_template_use_cases.py` extended):**
- Toggle on + `too_big` enqueues one job with the right args; toggle off enqueues nothing; `incoming` enqueues nothing; dry run enqueues nothing.
- The task builds `message` and `outcome` per decision (three strings pinned).
- Recipient chain: each missing link yields a skip reason and no send, no raise.
- Window open: `sent_as == "text"`, text equals the default message when no template is mapped; window closed with a mapped template: `sent_as == "template"`; the integration_log row carries the attempted payload in both, and a Respond error yields a `failed` row with the error message.
- `stock_ask_salesman` is a valid use case for `set_default`, and `USE_CASES` on the FE lists it (vitest on the dialog's list).

**Depends on:** S2 (the toggle), S3 (the decision), #1177 (the agent on the customer).

**Simplest thing, not built:** no retry beyond what the integration_log sweeper already does for `respond_io` rows; no digest ("3 asks today"); no in-app notification row (the salesman has no CRM login, ruling 2026-08-14 in `sales_agent.py`); no notification for `incoming`.

### S5 - the asks record: a sales-management function, minimal shape

The owner's ruling 5 makes this a durable business record, not a chatbot artefact, so by the uninstall test in PRINCIPLES it lives in `public` with normal FKs, not in the `chatbot` schema.

**Migration** `<n>_customer_stock_asks`:

```
customer_stock_asks
  id                 uuid PK
  company_id         uuid FK companies.id            (CompanyScopedMixin; the customer is company-scoped)
  customer_id        uuid FK customers.id ON DELETE CASCADE
  contact_id         text FK respond_contacts.id ON DELETE SET NULL   (who asked)
  sales_agent_id     uuid FK sales_agents.id ON DELETE SET NULL       (snapshot at ask time)
  turn_id            uuid FK chatbot.turns.id ON DELETE SET NULL      (cross-schema FK, the trace)
  product_id         uuid FK products.id ON DELETE SET NULL
  product_code       varchar(100)                                     (snapshot, survives a rename)
  quantity_asked     integer NOT NULL
  outcome            varchar(20) NOT NULL  CHECK in (too_big, in_stock, incoming, no_incoming, unassigned)
  eta_told           date NULL                                        (branch 3 only, already + Y)
  answer_text        text NOT NULL                                    (what the bot said, verbatim)
  notify_status      varchar(20) NOT NULL DEFAULT 'not_required' CHECK in (not_required, queued, sent, failed, skipped)
  notify_reason      varchar(60) NULL                                 (the skip reason or error head)
  notified_at        timestamp NULL
  follow_up_status   varchar(20) NOT NULL DEFAULT 'open' CHECK in (open, done)
  follow_up_note     text NULL
  followed_up_by     varchar(100) NULL FK users.id                    (who closed it; NULL until then)
  followed_up_at     timestamp NULL
  asked_at           timestamp NOT NULL
  created_at / updated_at
  indexes: (customer_id, asked_at desc), (sales_agent_id, follow_up_status), (turn_id)
```

Uuid `id` PK per ADR section 5. One row per (turn, product). Written by S3 in the same session as the turn's answer (every decision, notified or not, is a row: the record is "what was asked and answered", the notification is one column of it). S4's task updates `notify_status` / `notify_reason` / `notified_at` and the integration_log row moves to `business_table="customer_stock_asks"`, `business_id=ask.id`.

**Backend seam:** `GET /api/v1/order-management/customers/{id}/stock-asks` (list, paged, newest first, `list_query_registry` entry so the DataGrid column config works; gated by `order_management.customers.view`) and `PATCH /api/v1/order-management/customers/{id}/stock-asks/{ask_id}` with `{follow_up_status, follow_up_note}` (gated by `order_management.customers.edit`). Service `customer_stock_ask_service.py` (core). Rows carry `contact_name`, `sales_agent_code`, `product_code`, never a bare id.

**Frontend seam:** a "Stock asks" section on `CustomerDetail.tsx` (the page has cards, not tabs; a new card at full width below the two existing ones, always rendered, `-` when empty, per ADR 1f: "which questions did this customer ask the bot" is a question people open the record to answer). Records with a state the reader acts on are a DataGrid (ADR 1d), not a timeline: columns Asked at (absolute), Product, Qty, Outcome (status pill), ETA told, Notified (pill), Follow-up (pill) + a Mark done action that flips `follow_up_status` in place; `tableLayout` fixed + resizable, explicit sizes, truncate + title. No new page.

**Tests (pytest, `tests/test_customer_stock_asks_api.py`, `tests/chatbot/test_stock_ask_record.py`):**
- S3 writes one row per product decision with the right outcome, `eta_told` on branch 3 only, `answer_text` equal to the sent line; dry run / console writes nothing.
- S4 updates `notify_status` to `sent` / `failed` / `skipped` + reason; `not_required` on `incoming` and when the toggle is off.
- GET lists the customer's rows newest first with names not ids; a user in another company gets none (scope).
- PATCH flips follow-up, stamps `followed_up_by` / `_at`; without `.edit` it is 403; `done -> open` allowed.
- `test_schema_uuid_id_principle.py` passes without an exemption.
- Vitest: the section renders the grid, the empty state, and the Mark done flip.
- **Live console check (end of lane only):** `documentation/agents/chatbot-verification.md` with a new console case file `tests/chatbot/console_cases/<date>-stock-ask-v2.yaml`: four turns (one per branch) + the no-quantity ask, on the shared dev stack, evidence file under `documentation/plans/chatbot/evidence/`.

**Depends on:** S3, S4, PR #1177.

**Grill questions on its shape** (folded into the section below as G6 and G7): who closes a follow-up when salesmen have no CRM login; whether `open / done` is the whole state set for now; whether the section also lives on a per-agent view (#1170's salesman workspace) now or only on the customer page.

**Simplest thing, not built:** no per-agent workspace page (that is #1170's; this table is its seed and carries `sales_agent_id` so the page needs no migration). No assignment / reminder / SLA on follow-up. No edit of the ask itself (it is what happened). No export. No archive: the row is history; a deleted customer cascades it.

## Grill questions for the owner (max 8)

- **G1 - Stock location on the customer.** No column holds a customer's location today (`customers` has none; `sales_agents.location_group` is a NULL-everywhere ownership-group code; `stock_visibility_policies` is per contact). Accept `customers.stock_warehouse_id` as the one column, set on the customer form (no bulk tool)? And when it is NULL, is the answer "please refer to your salesman" with a notified skip reason (recommended), or should the bot fall back to the contact's visibility-policy warehouses the way #1118 does?
- **G2 - The trigger.** The four-branch flow replaces what `stock_denied` answers, so it fires on the same gate: global `chatbot_stock_denial_enabled` on AND the contact's "Stock checks" switch OFF. Is that right, and should the switch be relabelled "Stock numbers" (off = yes/no answers, on = full stock rows) so the two meanings do not read backwards? Related: PR #1118 (open, unmerged) answers a dealer's stock ask by the visibility policy's `availability` mode with per-product quantities. If both land, which path serves a dealer contact, or does #1118 fold into this?
- **G3 - NULL X and Y.** X NULL on both product and category = no cap (recommended), or = the assistant may not answer? Y NULL = 0 days? And the product's own category only, never its parent (recommended)?
- **G4 - "System ETA".** Recommend `COALESCE(eta_delay_date, estimated_arrival_date)` of the earliest still-incoming shipment that carries the product into the customer's assigned location (the same location scope as the stock check). Or any location? And the earliest shipment at all, or the earliest whose remaining quantity covers Q? Confirm ruling 3 means no threshold ever hides the date.
- **G5 - Notification shape.** One Respond use case `stock_ask_salesman` with an outcome phrase and a `message` slot (recommended), or three use cases? Confirm branch 3 (incoming) sends nothing, and that the in-stock branch does notify (the brief says yes).
- **G6 - Who works the asks record.** Salesmen have no CRM login (ruling 2026-08-14, `sales_agent.py`). Is the follow-up state worked by the office / account owner on the customer page for now, with #1170 deciding how an agent sees their own list (portal, login, or WhatsApp digest)?
- **G7 - Follow-up states.** `open / done` with a free-text note, nothing else, until #1170 defines the opportunity stages? Or should an ask be able to convert into a #1170 opportunity from day one (which pulls the opportunity table into this lane)?
- **G8 - Packing list toggle.** Does "packing list may be sent" mean only: on branch 3, attach the incoming shipment's packing-list file (which shows quantities) to the ETA answer? Or does it also govern the office incoming lane's attachments for that contact?

## Risks and rebase points

- PR #1118 (78 files, +18k) touches `head/parser.py`, `turn/state.py`, the stock MCP presenter and `engine.py`. It is not on main. S3 is written against main; if #1118 merges first, S3 reads per-product quantities off `entities[].quantity` and drops the scalar `demand_qty` read. One seam, named in the coder brief.
- PR #1177 adds `CustomerResponse.sales_agent_id/_code/_name`; S3's `stock_warehouse_*` fields ride the same response and form. Merge order: #1177 first.
- `answer.validator`'s "Total available quantity is N" line dies with this lane; its port-parity test (`tests/chatbot/test_s6c_answer_lane.py`) is flipped with the reason in the docstring, not deleted.

## Files (expected)

Backend: `app/models/product.py`, `app/models/access.py`, `app/models/order.py`, `app/models/customer_stock_ask.py` (new), `app/schemas/product.py`, `app/schemas/customer.py`, `app/schemas/customer_stock_ask.py` (new), `app/rbac/permission_registry.py`, `app/api/v1/master_data/categories.py`, `app/api/v1/master_data/products.py`, `app/api/v1/user_management/contacts.py`, `app/api/v1/order_management/customers.py`, `app/services/stock_ask_rules.py` (new), `app/services/customer_stock_ask_service.py` (new), `app/services/contact_service.py`, `app/services/chatbot/lanes/stock_ask.py` (new), `app/services/chatbot/engine.py`, `app/services/chatbot/turn_runtime.py`, `app/services/chatbot/turn/state.py`, `app/services/chatbot/lanes/business/answer.py`, `app/services/chatbot_reply_copy.py`, `app/models/respond_template.py`, `app/tasks/stock_ask_tasks.py` (new), `app/services/list_query_registry.py`, four migrations.
Frontend: `product-categories/components/CategoryForm.tsx`, `product-categories/[id]/page.tsx`, `products/components/ProductForm.tsx`, `products/[id]/components/ProductDetail.tsx`, `user-management/contacts/[id]/components/ContactChatbotSection.tsx` + service + hook, `order-management/customers/components/CustomerForm.tsx`, `CustomerDetail.tsx`, a new `CustomerStockAsksSection.tsx` + service + hook, `integration-management/whatsapp-templates` use-case list.
