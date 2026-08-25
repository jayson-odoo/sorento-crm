# UAC: Stock visibility policy

Plan: `PLAN-stock-visibility-policy.md`. Every criterion is testable; the test that proves it is
named in the right column and lands in Phase 2 (never deferred).

## Journey

**Actor 1: admin (CS lead).** Arrives at a contact's detail page from User Management > Contacts
because a user asked for the compact stock format. The page already knows the contact's access
types and companies. The Stock visibility section shows the policy the contact gets today and
where it comes from (Default / Access type / Contact override). One decision: pick a mode
(Detailed / Compact / Availability only). Optionally narrow the locations (or press "Dealer pool",
which fills BRW, MWH, DC1 from the warehouse `segment`). Save. Nothing else to configure; the
chatbot picks the policy up on the next message. Removing the override asks for confirmation and
the section falls back to the inherited policy. The same card, with the same two fields, sits on
each access type (to set the dealer default once) and in system settings (the global default).

**Actor 2: internal user on WhatsApp.** Types "check stock SRTBF11201-NEW". Gets either the
numbered per-location list (today) or, after the admin flipped them to Compact, the per-product
`Total / BRW / BRW-BB` block. Nothing to ask, nothing to choose.

**Actor 3: dealer on WhatsApp.** Types "do you have stock for SRTBF11201-NEW?". Bot: "How many
units do you need?". Dealer: "50". Bot: "Yes, we have stock." or "Sorry, we do not have enough
stock for that quantity." The dealer never sees a number and never sees a location.

**Told automatically:** nobody. A policy change is silent; it shows in the next reply. Audit
listeners record the policy row change like any other master-data edit.

## A. Policy resolution (backend, pytest `tests/test_stock_visibility_policy.py`)

| # | Given | When | Then | Test |
|---|---|---|---|---|
| A1 | Fresh DB after migration | resolve any contact | default row exists: `mode=detailed`, `warehouse_ids=NULL`, source `default` | `test_default_row_seeded_inert` |
| A2 | Contact override row `compact` AND access-type row `availability` for a type the contact holds | resolve | contact override wins (`compact`, source `contact`) | `test_contact_override_beats_access_type` |
| A3 | Contact holds `dealer` (availability, [BRW,MWH,DC1]) and `end_user` (detailed, NULL) | resolve | `availability`, warehouses = [BRW,MWH,DC1] (most restrictive mode, intersection of warehouses, NULL treated as "all") , source `access_type` | `test_multiple_access_types_most_restrictive` |
| A4 | No override, no access-type row | resolve | default row, source `default` | `test_falls_back_to_default` |
| A5 | `contact_id` given but not found (either id form, wrong `space_id`) | `GET /inventory/stock/balance` | zero rows, `stock_visibility` absent (fail-closed, matches company scope today) | `test_unresolvable_contact_fails_closed` |
| A6 | `contact_id` accepted as `respond_contacts.id` OR `respond_io_id` | resolve | same policy either way | `test_contact_id_both_forms` |
| A7 | Request has no `contact_id` (staff web UI) | `GET /inventory/stock/balance` | policy NOT applied even if the default row is `compact`: full rows, all RBAC-visible warehouses | `test_staff_path_ignores_policy` |

## B. Enforcement shapes (backend, same file)

| # | Given | When | Then | Test |
|---|---|---|---|---|
| B1 | Policy `detailed`, `warehouse_ids=[BRW, BRW-BB]`; stock exists in BRW, BRW-BB, DC1 | list | rows for BRW and BRW-BB only; `stock_visibility={mode:'detailed', warehouse_codes:['BRW','BRW-BB'], source}` | `test_detailed_filters_warehouses` |
| B2 | Policy `detailed`, `warehouse_ids=NULL` | list | all active warehouses (today's behaviour byte-for-byte) | `test_detailed_null_is_all` |
| B3 | Policy `compact`, product P with BRW=500, BRW-BB=200, BRW-IB=300, DC1=999 (DC1 not allowed) | list | `data=[]`, `total=0`, `stock_summary=[{product_code:P, total_on_hand:1000, locations:[{BRW,500},{BRW-BB,200},{BRW-IB,300}]}]`; DC1 absent; locations ordered by code | `test_compact_groups_and_sums_on_hand` |
| B4 | Policy `compact`, two products | list | two summary entries, one per product, each with its own total | `test_compact_multi_product_blocks` |
| B5 | `compact`, product has `quantity_reserved` > 0 | list | total uses `quantity_on_hand`, reserved ignored | `test_compact_uses_on_hand_not_available` |
| B6 | Policy `availability`, no `requested_qty` | list | `data=[]`, `stock_availability=[{product_code, needs_quantity:true, requested_qty:null, available:null}]`; **no key on the whole response body contains a quantity for that product** (assert by walking the JSON) | `test_availability_needs_quantity_no_leak` |
| B7 | `availability`, `requested_qty=50`, allowed on-hand sum = 60 | list | `available:true`, `needs_quantity:false`; still no quantity key anywhere | `test_availability_yes` |
| B8 | `availability`, `requested_qty=50`, allowed sum = 40, but a non-allowed warehouse holds 500 | list | `available:false` (non-allowed stock never counted) | `test_availability_no_ignores_disallowed_warehouses` |
| B9 | `availability`, `requested_qty=0` or negative | list | 422 | `test_requested_qty_validation` |
| B10 | Any mode | list | `last_updated_at` present and equals the BULK_IMPORT ledger timestamp, same as today | `test_last_updated_carried_on_every_mode` |
| B11 | `response_model` for the list route | schema | declares `stock_visibility`, `stock_summary`, `stock_availability` (lesson: undeclared fields vanish) | `test_response_model_declares_blocks` |
| B12 | Company scope: contact belongs to company C1; stock in C2 warehouses | list, any mode | C2 stock never in rows, summaries or availability sums | `test_policy_composes_with_company_scope` |

## C. CRUD API (backend)

| # | Criterion | Test |
|---|---|---|
| C1 | `PUT /inventory/stock-visibility/contacts/{id}` upserts `{mode, warehouse_ids}`; second PUT replaces `warehouse_ids` wholesale | `test_contact_policy_upsert` |
| C2 | `DELETE` removes the override; effective falls back to next tier | `test_contact_policy_delete_falls_back` |
| C3 | `PUT .../access-types/{code}` with unknown code -> 404; `mode` outside the three -> 422; unknown warehouse id -> 422 | `test_policy_validation` |
| C4 | `GET .../effective?contact_id&space_id` returns `{policy, source}`; usable without a staff JWT via integration API key | `test_effective_external` |
| C5 | Writes need `inventory.stock.edit`; reads `inventory.stock.view`; unauthenticated -> 401 | `test_policy_rbac` |
| C6 | Only one default row can exist (second insert fails on the partial unique) | `test_single_default_row` |

## D. MCP (pytest in `sorento_crm_mcp/tests/test_presenters_stock.py`)

| # | Criterion | Test |
|---|---|---|
| D1 | `crm_inventory_stock_balance_list` catalog lists `requested_qty` and forwards it | `test_catalog_requested_qty` |
| D2 | Raw response with `stock_visibility.mode=detailed` -> `result_type=stock`, envelope identical to before this change (golden fixture) | `test_render_detailed_unchanged` |
| D3 | `compact` -> `result_type=stock_compact`; item per product, `title=product_code`, fields `Total` first then locations in backend order, values plain ints | `test_render_compact` |
| D4 | `availability` needs_quantity -> `result_type=stock_availability`, intro "How many units do you need?", item `flags.needs_quantity=true`, no field with a numeric value | `test_render_availability_ask` |
| D5 | `availability` available true/false -> intro "Yes, we have stock." / "Sorry, we do not have enough stock for that quantity." | `test_render_availability_answer` |
| D6 | `stock_visibility` block passes through on every envelope | `test_envelope_passthrough` |

## E. Frontend (vitest + agent-browser evidence)

| # | Criterion | Proof |
|---|---|---|
| E1 | Contact detail page shows "Stock visibility" section with effective mode, warehouses (as `CODE - name`, never UUID) and a source badge | vitest `StockVisibilitySection.test.tsx`; browser run |
| E2 | Mode select is `SearchableSelect`, server-searched warehouses are a `SearchableMultiSelect` whose chips clear individually. Mode itself is NOT clearable: a policy row always has one, and the three options are the whole vocabulary | vitest |
| E3 | "Dealer pool" preset fills the `segment=dealer` warehouses | vitest |
| E4 | Save calls PUT, invalidates, toasts; error path uses `extractApiError` message | vitest |
| E5 | Remove override opens `ConfirmDeleteDialog` (never `confirm()`), then DELETE, then falls back to inherited policy in the UI | vitest |
| E6 | Same section (one component, `scope` prop) on the access-type page - via the row action dialog - and on the Settings > Stock Visibility tab; usable at 375px and 1280px, nothing clipped | browser run at both widths |
| E8 | Empty Locations reads "All locations" and saves `warehouse_ids: null`. The `[]` reading is out of scope for S1 (see the PLAN) | vitest |
| E7 | Navigation via sidebar from `/`, no deep URL | browser evidence |

## F. n8n (live-envelope harness + a real chat, evidence attached to the n8n PR)

| # | Criterion |
|---|---|
| F1 | `entity-ids-transformer` forwards `demand_qty` as `requested_qty`; absent -> not sent |
| F2 | `compact` reply reads exactly: product code line, `Total: N`, one `CODE: N` line per location, blank line between products, existing `_Data last updated_` footer |
| F3 | Dealer contact, "do you have stock for X" -> "How many units do you need?"; `session_vars.pending.intent == check_stock` written |
| F4 | Next message "50" -> yes/no reply, `pending` cleared, no quantity anywhere in the outbound text |
| F5 | Contact with `detailed` policy: outbound text byte-identical to before (regression via harness capture) |

## G. Roll-out gates

| # | Criterion |
|---|---|
| G1 | Deploy changes no outbound chatbot text for any contact (F5 on three live contacts) |
| G2 | One contact override flipped to `compact` changes only that contact |
| G3 | Default flipped to `compact` + overrides deleted = every non-dealer contact compact, staff web grid unchanged |
