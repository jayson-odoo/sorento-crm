# UAC - Chatbot stock ask v2: X threshold, Y ETA offset, contact toggles, salesman notification, asks record

Status: DRAFT, pre-grill (24 Sep 2026). Plan: `PLAN-chatbot-stock-ask-v2-24sep.md`. Issue #1168.
Numbering: AC-SA<slice><nn>. Tags: [BE] pytest, [FE] vitest, [E2E] recorded agent-browser or console evidence, [T] a test that exists only to pin a rule.
Every AC below answers to a step in the Journey. Open owner questions are G1 to G8 in the plan; an AC that depends on one names it.

## Journey

Actor: a dealer contact on WhatsApp. The system already knows: which customer they act for (`respond_contact_customers`), that customer's sales agent (#1177) and stock location (S3), the product's X and Y (S1), and whether this contact's salesman wants to hear about asks and whether the packing list may go out (S2). The dealer is asked for exactly one thing they alone know: the quantity.

1. **Ask.** The dealer writes "do you have MSK11A-QT, 150 pcs". (If no quantity: the bot asks "Please specify your demand quantity" once and waits; nothing else changes.)
2. **Decide.** The bot reads Q = 150, X and Y for the product, on hand at the customer's location, and the next dated incoming shipment into that location. It picks one of four answers. No number of ours is ever composed into the reply.
3. **Answer.** One sentence per product, fixed wording (rewordable on Settings > AI Prompts), sent as the turn's reply.
4. **Notify.** If the contact's "Notify salesman" is on and the answer was too big / in stock / no incoming, the customer's sales agent gets one WhatsApp line through their Respond contact: text inside the 24h window, the mapped template outside it. Sent after the customer's reply, never blocking it.
5. **Record.** Every decision is a row on the customer: what was asked, when, what was answered, whether the salesman was told, follow-up open.
6. **Work it.** The office opens the customer, sees "Stock asks", marks a row done with a note.
7. **Configure (once).** An admin with the stock-rules permission sets X and Y on a category (and overrides on a product); a contacts editor flips the two toggles on the contact; the customer editor sets the stock location and the sales agent.

## S1 - X and Y on categories and products

- **AC-SA101 [BE][T]** Given a product with `chatbot_max_qty = 200` in a category with `chatbot_max_qty = 50`, When `effective(product)` runs, Then `max_qty` is 200 (product overrides category).
- **AC-SA102 [BE][T]** Given a product with NULL `chatbot_max_qty` in a category with 50, Then `max_qty` is 50; Given both NULL, Then `max_qty` is None. Same table for `eta_offset_days`. Zero is a value, not NULL.
- **AC-SA103 [BE][T]** Given a product whose category has NULL X but whose parent category has X = 30, Then `max_qty` is None (no tree walk; pending G3).
- **AC-SA104 [BE]** Given a user holding `master_data.products.chatbot_stock_rules`, When they PUT a category with new X and Y, Then 200 and the response carries both values.
- **AC-SA105 [BE]** Given a user with `master_data.product_categories.edit` but not the stock-rules slug, When they PUT a category whose body changes X, Then 403 with an `AppException` message naming the permission; When their body carries the current X unchanged, Then 200.
- **AC-SA106 [BE]** AC-SA104 and AC-SA105 hold for PUT product against `master_data.products.edit`.
- **AC-SA107 [BE]** Given a product with NULL X in a category with X = 50, When GET product, Then the response carries `chatbot_max_qty: null`, `chatbot_max_qty_effective: 50`, and the two ETA fields likewise (asserted field by field; `response_model` drops what is undeclared).
- **AC-SA108 [BE]** After the migration, `user_permissions` holds `master_data.products.chatbot_stock_rules`; every role holding `master_data.products.edit` holds it; a role whose slug starts with `integration_` does not; `admin` does.
- **AC-SA109 [BE]** A negative X or Y is rejected at the API (422) and at the database (CHECK).
- **AC-SA110 [FE]** `CategoryForm` renders "Max quantity the assistant answers" and "ETA offset (days)"; without the permission both inputs are disabled and show the stored value; with it they are editable. No helper text explaining the feature.
- **AC-SA111 [FE]** `ProductForm` Basic Information shows the same two inputs beside the reorder fields, with the category's effective value as placeholder when the product value is empty; `ProductDetail` shows the two facts in the same section, same order, `-` when unknown.
- **AC-SA112 [E2E]** Sidebar to Master Data > Product Categories, open a category, set X = 200, Y = 7, save, reopen: both persist; at 375px the modal scrolls to its Save.

## S2 - per-contact toggles

- **AC-SA201 [BE]** Given a contact, When PUT `/contacts/{id}/chatbot` with `{"chatbot_notify_salesman": true}`, Then the response and a following GET carry `chatbot_notify_salesman: true` and `chatbot_packing_list_allowed` unchanged (absent = leave alone).
- **AC-SA202 [BE]** Given a migrated row, Then both toggles read `false` (server default), and GET contact lists both keys (manual dict builder).
- **AC-SA203 [BE]** Given a contact with both toggles on, When `turn_runtime.load_profile` runs (workspace-scoped and NULL-workspace fallback), Then `Profile.notify_salesman` and `Profile.packing_list_allowed` are true; an unknown contact yields false for both.
- **AC-SA204 [BE]** PUT without `user_management.contacts.edit` is 403 (existing gate, re-pinned for the new fields).
- **AC-SA205 [FE]** `ContactChatbotSection` renders "Notify salesman on stock asks" and "Packing list may be sent" switches; toggling one saves the whole profile with the other values unchanged.
- **AC-SA206 [E2E]** Sidebar to User Management > Contacts, open a contact, Access > Chatbot, flip "Notify salesman on stock asks", reload: it stays on.

## S3 - the four-branch decision

Decision truth table (pending G3 for NULL X, G4 for the ETA source):

| # | Q | X | available at location | ETA | Y | result | eta_told |
|---|---|---|---|---|---|---|---|
| 1 | 250 | 200 | 1000 | any | any | too_big | - |
| 2 | 200 | 200 | 200 | any | any | in_stock | - |
| 3 | 150 | 200 | 149 | 2026-10-12 | 7 | incoming | 2026-10-19 |
| 4 | 150 | 200 | 0 | none | any | no_incoming | - |
| 5 | 5000 | NULL | 1 | 2026-10-12 | 0 | incoming | 2026-10-12 |
| 6 | 150 | 200 | 149 | 2026-10-28 | 5 | incoming | 2026-11-02 |
| 7 | 150 | 200 | 149 | 2026-10-12 | NULL | incoming | 2026-10-12 |

- **AC-SA301 [BE][T]** `decide()` returns every row of the table above.
- **AC-SA302 [BE]** Given the switch on and a contact with "Stock checks" off, and a turn "do you have MSK11A-QT" with no quantity, Then the turn routes to `demand_qty` and replies with the `demand_qty` copy; nothing is recorded, nothing notified.
- **AC-SA303 [BE]** Given the same contact and "MSK11A-QT 250 pcs" with X = 200, Then the reply is the `stock_ask_too_big` copy rendered with product and quantity, `branch_kind` stays `stock_denied`, and no stock row is fetched (the MCP stock tool is not called).
- **AC-SA304 [BE]** Given available 200 at the customer's location, Q = 200, Then `stock_ask_in_stock`.
- **AC-SA305 [BE]** Given available 0 at the customer's location and 500 at another warehouse, Q = 10, Then NOT `in_stock` (location scope, ruling 2).
- **AC-SA306 [BE]** Given no stock and a still-incoming shipment carrying the product into the customer's location with `estimated_arrival_date = 2026-10-12`, `eta_delay_date = 2026-10-20`, Y = 7, Then the reply is `stock_ask_incoming` with `27/10/2026` (the delay date wins, plus Y).
- **AC-SA307 [BE]** Given no stock and the only incoming shipment goes to another warehouse, Then per G4's answer either `no_incoming` (recommended) or `incoming`; the test is written for the ruled answer and the other assertion is deleted, not skipped.
- **AC-SA308 [BE]** Given no stock and a shipment with remaining quantity but neither ETA date, Then `no_incoming` (an undated shipment is not an ETA).
- **AC-SA309 [BE]** Given no stock and no incoming, Then `stock_ask_no_incoming`.
- **AC-SA310 [BE][T]** For every branch, the reply text contains no digit sequence other than the quantity asked and the ETA date (regex guard over the composed reply).
- **AC-SA311 [BE]** Given the contact is linked to no customer, or the customer has NULL `stock_warehouse_id`, Then the reply is `stock_ask_unassigned` and the recorded outcome is `unassigned` with reason `no_customer` / `no_location` (pending G1).
- **AC-SA312 [BE]** Given a contact with "Stock checks" ON, Then the turn never enters the arm and the existing stock answer is unchanged; Given the global switch off, likewise.
- **AC-SA313 [BE]** Given a turn naming two products with Q = 100, Then the reply is two lines in the order named, each decided on its own X, stock and ETA.
- **AC-SA314 [BE]** Given branch 3 and `Profile.packing_list_allowed` true, Then the turn's actions carry the shipment's packing-list attachment; false, no attachment (pending G8).
- **AC-SA315 [BE]** The five `stock_ask_*` copy keys are registered in `CHATBOT_REPLY_COPY` with their tokens, seeded by the registry migration, and resolvable through `copy.resolve(db)`; an edited registry body is what the turn renders.
- **AC-SA316 [BE]** `answer.validator` no longer prints "Total available quantity is N" for a denied contact; the parity test in `test_s6c_answer_lane.py` is flipped with the reason in its docstring.
- **AC-SA317 [BE]** PUT customer with `stock_warehouse_id` of an active warehouse in scope persists and the response carries `stock_warehouse_id` + `stock_warehouse_code`; an unknown id is 422; an inactive warehouse is 422; null clears it.
- **AC-SA318 [FE]** `CustomerForm` renders "Stock location" as a clearable `SearchableSelect` (code - name), preselected on edit; `CustomerDetail` Contact Information shows the code - name or `-`.
- **AC-SA319 [E2E]** Sidebar to Order Management > Customers, open a customer, Edit, set Stock location, save: the detail shows it; at 375px nothing clips.
- **AC-SA320 [BE]** Console dry run (`dry_run=True`) of any branch composes the reply and writes no ask row and enqueues no notification.

## S4 - salesman notification

- **AC-SA401 [BE]** Given "Notify salesman" on and outcome `too_big`, When the turn completes, Then exactly one `notify_salesman` job is enqueued on the `respond_io` queue carrying the ask (or turn + product on S4 alone); Given the toggle off, none; Given outcome `incoming`, none (pending G5); Given a dry run, console or test turn, none.
- **AC-SA402 [BE][T]** The task renders `message` and `outcome` per decision exactly as the plan's S4 table states, with `customer_name`, `product` (code - name) and `quantity` filled.
- **AC-SA403 [BE]** Recipient chain, one test per missing link: contact with no customer, customer with no sales agent, sales agent with no `contact_id`, contact with no `respond_io_id`. Each yields no send, a warning log, and status `skipped` with that reason; nothing raises.
- **AC-SA404 [BE]** Given the agent contact's window is open and no template is mapped, When the task runs, Then `send_text_or_template` is called with `use_case="stock_ask_salesman"` and the send is `sent_as: text` with the default message; the `integration_log` row is `respond_io` / outbound / `success` with that text as `request_payload`.
- **AC-SA405 [BE]** Given the window is closed and an approved template is mapped to `stock_ask_salesman` with `message` and `contact_name` slots, Then the send is `sent_as: template` and the log row carries the template payload.
- **AC-SA406 [BE]** Given the window is closed and no template is mapped, Then the send is skipped (`TemplateSendSkipped`), the log row is `failed` with the error message, and the ask's notify status is `failed`.
- **AC-SA407 [BE]** Given Respond returns 401, Then the log row is `failed` with `status_code 401` and the response body, and the customer's own reply (already sent) is unaffected.
- **AC-SA408 [BE]** `stock_ask_salesman` is accepted by `set_default` and listed by the defaults endpoint; **[FE]** the Set Default Template dialog lists it with a label.
- **AC-SA409 [BE]** The notification is enqueued only after the turn row is written (`status = done`): a test that fails the tail before the write sees no job.

## S5 - the asks record

- **AC-SA501 [BE]** Given a live (non-test, non-console) turn that reached any of the five outcomes, Then one `customer_stock_asks` row exists per product with `customer_id`, `contact_id`, `sales_agent_id` (snapshot), `turn_id`, `product_id`, `product_code`, `quantity_asked`, `outcome`, `answer_text` equal to that product's reply line, `asked_at` = the turn's time, `follow_up_status = open`.
- **AC-SA502 [BE]** `eta_told` is set on `incoming` only and equals the date told (already + Y); NULL on every other outcome.
- **AC-SA503 [BE]** `notify_status` is `not_required` when the toggle is off or the outcome is `incoming`; `queued` when a job was enqueued; the task moves it to `sent` (+ `notified_at`), `failed` (+ reason head) or `skipped` (+ reason).
- **AC-SA504 [BE]** The S4 `integration_log` row references `business_table = customer_stock_asks`, `business_id = ask.id`.
- **AC-SA505 [BE]** GET `/customers/{id}/stock-asks` lists the rows newest first, paged, with `contact_name`, `sales_agent_code`, `product_code` and no bare ids; requires `order_management.customers.view`; a caller scoped to another company sees none.
- **AC-SA506 [BE]** PATCH `/customers/{id}/stock-asks/{ask_id}` with `{"follow_up_status": "done", "follow_up_note": "called, quoted 150"}` stamps `followed_up_by` / `followed_up_at`; `done -> open` is allowed; without `order_management.customers.edit` it is 403; an ask belonging to another customer is 404.
- **AC-SA507 [BE][T]** `test_schema_uuid_id_principle.py` passes with no new exemption; the `list_query_registry` entry serializes the row.
- **AC-SA508 [FE]** `CustomerDetail` always renders a "Stock asks" section: a DataGrid (fixed layout, resizable, explicit sizes, truncate + title) with Asked at (absolute), Product, Qty, Outcome pill, ETA told, Notified pill, Follow-up pill and a Mark done action that flips the row in place; `-` when there are no rows.
- **AC-SA509 [E2E]** Sidebar to Order Management > Customers, open the customer used in the console check: the four console turns appear as four rows with the right outcomes; Mark done flips one; at 375px the grid scrolls horizontally without clipping the page.
- **AC-SA510 [E2E] Live console check (end of lane only).** Per `documentation/agents/chatbot-verification.md`: console case file `tests/chatbot/console_cases/<date>-stock-ask-v2.yaml` with five turns (no quantity; too big; in stock; incoming with the +Y date; no incoming) against a dealer contact with the switch on, "Stock checks" off, "Notify salesman" on, on the shared dev stack; the salesman contact receives three lines; evidence recorded under `documentation/plans/chatbot/evidence/`.

## Definition of Done for the lane

- Every AC above green or explicitly re-ruled by the owner in this file's decision table (to be added at grill).
- Both migrations chain onto main's single head (`./scripts/alembic-reparent.sh`), `alembic heads` shows one.
- New permission swept (AC-SA108). New columns on every manual dict builder (AC-SA107, AC-SA202).
- Reviewer + security-reviewer (the diff touches RBAC and an outbound send surface) + browser pass at 375px and 1280px, once per lane.
- PR body names the track (full), the plan created timestamp, and this file.
