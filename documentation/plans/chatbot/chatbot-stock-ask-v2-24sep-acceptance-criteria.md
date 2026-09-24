# UAC - Chatbot stock ask v2: four-branch answer, X cap, Y ETA offset, contact toggles, salesman notification, asks record

Status: grilled 24 Sep 2026, ready for tickets. Plan: `PLAN-chatbot-stock-ask-v2-24sep.md`. Issue #1168. Rulings R1 to R11 (quoted in the plan) are binding.
Numbering: AC-SA<slice><nn>, slices S0 to S6. Tags: [BE] pytest (Postgres), [FE] vitest, [E2E] recorded agent-browser or console evidence, [T] a test that exists only to pin a rule. The `tester` writes every [BE]/[FE] test red before the `coder` starts the slice.

## Journey

Actor: a dealer contact on WhatsApp whose stock visibility policy mode is "Availability only" (R1). The system knows the contact's policy locations (R3), the customer they act for, that customer's sales agent (#1177), each product's X and Y (S1), and the contact's two toggles (S2).

1. **Ask.** The dealer names one or more products. #1118's stock task collects a quantity per product (unchanged, R1).
2. **Decide.** Per product with quantity Q: X and Y resolved (product, else own category, else 0); available = on hand in the policy locations minus open SO (R4); the earliest non-draft still-incoming shipment with a packing list, any location (R5).
3. **Answer.** One R6 sentence per product in the order named. No number of ours except Q and the ETA date.
4. **Attach.** B3 only, and only when "Packing list allowed" is on: the shipment's packing list is sent.
5. **Notify.** B1, B2, B4 only, and only when "Notify salesman" is on: the customer's sales agent gets one WhatsApp message (template outside the window, text inside), logged in `integration_log`.
6. **Record.** Every answered ask is a `stock_asks` row, state open.
7. **Work it.** The office sets state and note on the customer's Asks tab; the sales agent does the same on the portal's Customer asks page.
8. **Configure (once).** A holder of `master_data.chatbot_stock_limits.edit` sets X and Y on a category (and overrides on a product); a contacts editor flips the two toggles; an admin maps a template to `stock_ask_salesman`.

## S0 - Rebase and merge #1118

- **AC-SA001 [BE]** `feat/chatbot-dealer-stock-verdict` carries main, `alembic heads` shows one head with `dsv_0001` re-parented, and #1118's suites pass on the rebased head in CI.
- **AC-SA002 [BE]** #1118 is merged to main before any S1 to S6 commit lands on the v2 lane.

## S1 - X and Y columns, permission, forms

- **AC-SA101 [BE][T]** `effective()`: product X = 200, category X = 50 -> 200; product NULL, category 50 -> 50; both NULL -> 0. Same for Y. Zero set explicitly is 0 and wins over the category.
- **AC-SA102 [BE][T]** Product NULL, own category NULL, parent category X = 30 -> 0 (no parent walk, R2).
- **AC-SA103 [BE]** After the migration the four columns exist, nullable, and a negative value is rejected by the DB CHECK.
- **AC-SA104 [BE]** `user_permissions` holds `master_data.chatbot_stock_limits.{view,add,edit,delete}`; every role holding `master_data.products.edit` and `admin` hold `.view` and `.edit`; an `integration_*` role holds neither.
- **AC-SA105 [BE]** With `.edit`, PUT category with X = 200, Y = 7 -> 200 and the response carries both.
- **AC-SA106 [BE]** Without `.edit`, PUT category changing X -> 403 (`AppException`, message names the permission); carrying the unchanged X -> 200.
- **AC-SA107 [BE]** AC-SA105 and AC-SA106 hold for PUT product.
- **AC-SA108 [BE]** A negative X or Y at the API -> 422. GET category and GET product carry `chatbot_max_qty` and `chatbot_eta_offset_days` (asserted field by field).
- **AC-SA109 [FE]** `CategoryForm` shows "Max quantity (assistant)" and "ETA offset (days)" only with `.view`; the inputs are disabled without `.edit`. No helper text.
- **AC-SA110 [FE]** `ProductForm` Basic Information shows the two inputs beside the reorder fields, placeholder = the category value when empty; the product view shows the same fields in the same place and order, `-` when unset.
- **AC-SA111 [E2E]** Sidebar to Master Data > Product Categories, open a category, set X and Y, save, reopen: persisted; at 375px the modal reaches Save; the product form shows the category placeholder.

## S2 - Contact toggles

- **AC-SA201 [BE]** PUT `/contacts/{id}/chatbot` `{"notify_salesman": true}` persists and returns it; `packing_list_allowed` unchanged (absent = leave alone).
- **AC-SA202 [BE]** A migrated contact reads both false; GET contact lists both keys (dict builder).
- **AC-SA203 [BE]** Without `user_management.contacts.edit` the PUT is 403.
- **AC-SA204 [BE]** `load_profile` returns `notify_salesman` and `packing_list_allowed` for a workspace row and for the NULL-workspace fallback; an unknown contact yields false for both.
- **AC-SA205 [FE]** `ContactChatbotSection` renders "Notify salesman" and "Packing list allowed" switches; toggling one saves the whole profile with the others unchanged. **[E2E]** Sidebar to User Management > Contacts, open a contact, flip "Notify salesman", reload: still on.

## S3 - Four-branch verdict and the R5 ETA read

Truth table for `branch()` (x and y already resolved; unset = 0):

| # | Q | X | available | shipment (date) | Y | branch | told |
|---|---|---|---|---|---|---|---|
| 1 | 250 | 200 | 1000 | 2026-10-12 | 7 | too_big | - |
| 2 | 5 | 0 (unset) | 1000 | none | 0 | too_big | - (cap_unset) |
| 3 | 200 | 200 | 200 | none | 0 | in_stock | - |
| 4 | 150 | 200 | 149 | 2026-10-12 | 7 | incoming | 19/10/2026 |
| 5 | 150 | 200 | 149 | 2026-10-28 | 5 | incoming | 02/11/2026 |
| 6 | 150 | 200 | 0 | none | 7 | no_incoming | - |
| 7 | 150 | 200 | 0 | 2026-10-12 | 0 (unset) | incoming | 12/10/2026 |
| 8 | 1 | 1 | -3 (SO over on hand) | none | 0 | no_incoming | - |

- **AC-SA301 [BE][T]** `branch()` returns every row above.
- **AC-SA302 [BE]** Available counts only the contact's policy locations: 0 in the policy set and 500 elsewhere, Q = 10, X = 100 -> not `in_stock`.
- **AC-SA303 [BE]** Open sales order lines in the policy set are subtracted: on hand 100, open SO 60, Q = 50 -> not `in_stock`; Q = 40 -> `in_stock`.
- **AC-SA304 [BE]** ETA shipment: of two qualifying shipments (non-draft, line not received, remaining > 0, `attachment_id` set) with `estimated_arrival_date` 2026-11-01 and 2026-10-12, the 2026-10-12 one is used.
- **AC-SA305 [BE]** An earlier shipment WITHOUT `attachment_id` is ignored; a draft shipment is ignored; a line with `line_status = received` is ignored; a line with `quantity_received = quantity_shipped` is ignored. With no other shipment the branch is `no_incoming`.
- **AC-SA306 [BE]** `eta_delay_date` is never read: a shipment with `estimated_arrival_date` 2026-10-12 and `eta_delay_date` 2026-10-20, Y = 0 -> told 12/10/2026.
- **AC-SA307 [BE]** A qualifying shipment whose line is allocated to a warehouse OUTSIDE the policy set still yields `incoming` (ANY location, R5).
- **AC-SA308 [BE]** Open `spo_allocations` and open purchase order lines alone produce `no_incoming` (never a source, R5).
- **AC-SA309 [BE]** A qualifying shipment with NULL `estimated_arrival_date` sorts after dated ones; when it is the only one the branch is `incoming` with no `eta`, and the line reads "No stock at the moment, ETA to be confirmed." (plan risk; owner may re-rule).
- **AC-SA310 [BE]** Entry shape: `branch`, `cap_unset`, `category_name`, `eta` (incoming only, dd/mm/yyyy), `packing_list` (see AC-SA311); `verdict`, `running_low`, `disclaimer`, `available` are gone; `needs_quantity` and `requested_qty` unchanged so `StockQtyTask` still opens, fills and closes (#1118 task suites green).
- **AC-SA311 [BE]** `packing_list` (`filename`, `file_path`, `mime_type`) is present on an `incoming` entry only when the asking contact's `packing_list_allowed` is true; absent otherwise and on every other branch.
- **AC-SA312 [BE][T]** No entry field and no presenter line carries a quantity of ours: a regex guard over the rendered reply finds no digits except Q and the date.
- **AC-SA313 [BE]** MCP presenter renders, per entry in asked order: B1 "The quantity is more than what I can confirm here, please refer to your salesman."; B2 "Yes, we have stock for <code> x <Q>, please refer to your salesman to proceed."; B3 "No stock at the moment, ETA <dd/mm/yyyy>."; B4 "No stock and no incoming at the moment, please refer to your salesman." No "running low", no "purchase", no UUID.
- **AC-SA314 [BE]** Engine: B3 with `packing_list` present emits one `send_attachments` action with that file; without it, no attachment action.
- **AC-SA315 [BE]** `detailed` and `compact` payloads are unchanged (R10); the `stock_denied` / `demand_qty` suites on `chatbot_stock_denial_enabled` pass unchanged (R1).
- **AC-SA316 [BE]** `stock_verdict.py` and `tests/test_stock_verdict.py` are gone; nothing imports `stock_verdict`.
- **AC-SA317 [BE]** After `sa2_0003`, `system_settings.chatbot_stock_low_threshold_pct` does not exist and neither settings dict builder emits it. **[FE]** Settings > Chatbot renders without the threshold card.
- **AC-SA318 [E2E]** Console check per `documentation/agents/chatbot-verification.md` against an "Availability only" dealer contact: one turn per branch (B1 via Q > X, B1 via unset X, B2, B3 with toggle on and off, B4); replies quoted in `documentation/plans/chatbot/evidence/`.

## S4 - Agent notification + integration_log

- **AC-SA401 [BE]** `notify_salesman` on: B1, B2, B4 each enqueue exactly one `notify_salesman` job on `respond_io`; B3 enqueues none; toggle off enqueues none; dry run, console and test turns enqueue none.
- **AC-SA402 [BE]** The job is enqueued only after the turn row is written: a turn that fails before the write enqueues nothing.
- **AC-SA403 [BE][T]** Outcome phrase: B2 `in stock`, B1 with X set `too big`, B1 with `cap_unset` `no cap set for <category name>`, B4 `no stock no incoming`. Context vars carry `customer_name`, `contact_name`, `product` (code - name), `quantity`, `asked_at`.
- **AC-SA404 [BE]** Recipient chain, one test per missing link (no customer, customer without `sales_agent_id`, agent without `contact_id`, agent contact without `respond_io_id`): no send, warning log, skip reason recorded, no raise.
- **AC-SA405 [BE]** Window open: `send_text_or_template` called with `use_case="stock_ask_salesman"`, `sent_as == "text"`; one `integration_log` row, `respond_io` / outbound / success, payload = the text.
- **AC-SA406 [BE]** Window closed + mapped template: `sent_as == "template"`, log row carries the template payload.
- **AC-SA407 [BE]** Window closed + no mapped template: `TemplateSendSkipped`, log row failed with the message.
- **AC-SA408 [BE]** Respond 401: log row failed with status and body; the dealer's reply is unaffected.
- **AC-SA409 [BE]** `stock_ask_salesman` is in `TEMPLATE_DEFAULT_USE_CASES` and accepted by `set_default`. **[FE]** The Set Default Template dialog lists it with its label.
- **AC-SA410 [E2E]** With a template mapped, a B2 console turn on a live contact with a linked agent delivers one message to the agent's Respond contact; the `integration_log` row is visible in the Respond outbox.

## S5 - Asks table + CRM Asks tab

- **AC-SA501 [BE]** A live turn answering N products writes N `stock_asks` rows with `customer_id`, `contact_id`, `product_id`, `product_code`, `quantity`, `branch`, `answer_summary` (the exact line sent), `state = open`; dry run and console write none.
- **AC-SA502 [BE]** At write: B3 `notified_agent = false`, `notify_skip_reason = not_notified_branch`; toggle off `toggle_off`. The S4 task sets `notified_agent = true` on success, or the skip / failure reason.
- **AC-SA503 [BE]** A contact with no resolvable customer still gets a row with `customer_id` NULL and reason `no_customer`.
- **AC-SA504 [BE]** The S4 `integration_log` row has `business_table = stock_asks`, `business_id = ask.id`.
- **AC-SA505 [BE]** GET `/order-management/customers/{id}/asks`: newest first, paged, `contact_name` and `product_code`, no bare ids; 403 without `order_management.customers.view`; a user scoped to another company sees none.
- **AC-SA506 [BE]** PATCH `/order-management/customers/{id}/asks/{ask_id}` `{state: done, note}` persists; `done -> open` allowed; 403 without `order_management.customers.edit`; ask of another customer 404; state outside open / done 422.
- **AC-SA507 [BE][T]** `test_schema_uuid_id_principle.py` passes with no exemption; the `list_query_registry` entry serializes a row.
- **AC-SA508 [FE]** `CustomerDetail` has line tabs "Details" (the existing two cards, unchanged) and "Asks".
- **AC-SA509 [FE]** Asks tab: DataGrid fixed layout, resizable, explicit sizes, truncate + title; columns Asked at, Contact, Product, Qty, Branch (Badge), Answer, Notified (Badge, reason in title), State, Note; empty state when no rows.
- **AC-SA510 [FE]** With `.edit`, State (required `SearchableSelect`) and Note are editable in place and save through the mutation hook (invalidate + toast); without `.edit` the same cells render read-only values.
- **AC-SA511 [E2E]** Sidebar to Order Management > Customers, open the console-check customer, Asks tab: the S3 console turns appear with the right branches; set one to done with a note, reload: persisted. 375px and 1280px: no page clipping.
- **AC-SA512 [BE]** Deleting a customer removes its asks (CASCADE).

## S6 - Portal "Customer asks" page

- **AC-SA601 [BE]** `sales_agent_for_contact` is the single agent resolution used by both `lookup_debtors_for_agent` and the new routes; the existing debtor lookup tests pass unchanged.
- **AC-SA602 [BE]** GET `/public/portal/customer-asks` as an agent's linked contact lists asks whose customer's `sales_agent_id` is that agent, newest first, paged; asks of other agents' customers and of customer-less rows are absent.
- **AC-SA603 [BE]** A portal contact with no linked agent gets 403 `NOT_A_SALES_AGENT` on GET and PATCH.
- **AC-SA604 [BE]** PATCH `/public/portal/customer-asks/{ask_id}` `{state, note}` persists for an in-scope ask; an out-of-scope ask is 404; a bad state is 422.
- **AC-SA605 [FE]** `CustomerAsksList` renders the portal DataGrid (PortalLanding list pattern) with Asked at, Customer, Contact, Product, Qty, Branch, Answer, Notified, State, Note; empty state; State and Note editable in place.
- **AC-SA606 [FE]** The portal nav shows "Customer asks" only for a linked agent contact.
- **AC-SA607 [E2E]** Log into the portal as the agent's contact, open Customer asks, mark the S5 row done: the CRM Asks tab shows the same state and note; 375px usable.

## Definition of Done for the lane

- Every AC green, or re-ruled by the owner in this file.
- All four migrations chain onto main's single head (`./scripts/alembic-reparent.sh`), `alembic heads` shows one.
- New columns on every manual dict builder (AC-SA108, AC-SA202); dropped column off both settings builders (AC-SA317).
- Reviewer + security-reviewer (RBAC, outbound send, per-contact attachment release, portal scope) + browser pass at 375px and 1280px, once per lane.
- PR body names the track (full), this file and the plan.
