# PLAN: Stock visibility policy (per contact, per access type)

**Status:** Approved 2026-08-25. Tickets #291 (S1) #292 (S2) #293 (S3) #294 (S4) #295 (S5) #296 (S6). S1 code complete (Phase 1), S2 done (backend + pytest, migration `416_stock_visibility_policy`), S3 done, S4 next.
**UAC:** `stock-visibility-policy-acceptance-criteria.md` (alongside)
**Domain:** inventory / chatbot (n8n `sub-get-results` `Fss5aAaXthJSWpZCgKiKR`, MCP `crm_inventory_stock_balance_list`)

## Problem

A Respond.io contact asking the chatbot "check stock X" today gets every active location's
on-hand quantity in one fixed numbered-list format. Three asks landed at once:

1. **Location control.** Which warehouses/locations a contact may see must be configurable
   per contact (and, to scale to dealers, per contact access type).
2. **Second response format.** One user prefers a compact `Total / per-location` block. Must be
   switchable per contact so it can be A/B'd on one user, then rolled out, then the legacy
   format phased out.
3. **Dealers must never see quantities.** Dealer asks "do you have stock?" -> bot asks "how
   many?" -> dealer answers a number -> bot says yes / no, judged against the dealer pool
   locations (BRW, MWH, DC1 combined) only.

## Decisions (grilled 2026-08-25)

| Question | Decision |
|---|---|
| Quantity basis | `quantity_on_hand` (today's basis). Not `quantity_available`. |
| Availability yes/no can be binary-searched to the real qty | Accepted for v1. |
| Compact format, several products | One block per product, repeated. |
| Policy tiers | contact override > contact access type > global default. All three in v1 (access-type tier is what makes dealers scale: one row for `dealer`, not one per dealer). |
| Dealer pool | All dealers see the combined BRW + MWH + DC1 total. No per-region split in v1. |
| Where enforced | Backend, inside `GET /inventory/stock/balance`. n8n and MCP only present. Same doctrine as `agent_field_access` (LESSONS: preflight is a convenience, never the mechanism). |

## What exists (the seams)

- `contact_id` + `space_id` already ride every stock call: MCP catalog
  `crm_inventory_stock_balance_list` (`sorento_crm_mcp/catalog.py:429-450`); n8n
  `entity-ids-transformer` sets both (`space_id` hardcoded `"364817"`, single tenant, deliberate).
  Backend reads them **globally** for company scoping only (`app/services/company_scope_resolver.py:192`).
- `view=render` is MCP-side only: injected/popped in `server.py:1566-1684`, rendered by
  `presenters.py:_stock()` (line 764) into a markdown-free `{result_type, intro, items[{fields[{label,value}], flags}], last_updated_at}`
  envelope. n8n `output-structurer` prints `*label:* value` lines and appends
  `_Data last updated: ..._`. **Skin = n8n, shape = MCP, data = backend.**
- Warehouse model already carries the pool concept, stored not parsed:
  `warehouses.pool_warehouse_id` (self FK) and `warehouses.segment` (`dealer` = bare site code
  BRW / MWH / DC1, `project` = BRW-BB etc.), `app/models/inventory.py:39-56`.
- Reformulator (`sub-query-reformulator`) already emits `demand_qty`; `entity-ids-transformer`
  **drops it**. That is the missing input for the dealer yes/no.
- Precedent for default-row + per-contact override: `agent_field_access` (`app/models/access.py:424`),
  resolver `field_access.resolve_contact_id` (accepts `respond_contacts.id` OR `respond_io_id`,
  `space_id` disambiguates), enforcement `apply_field_access` on `/incoming-stock/list`.
- Contact access types: `contact_access_types` (code PK: `end_user`, `dealer`, `sorento_dealer` ...)
  M2M via `respond_contact_access_types`.
- Cross-turn pending question slot: `respond_contacts.session_vars` JSONB via
  `GET|PUT /api/v1/external/conversation-variables/{respond_io_id}`.
- Admin surface precedent: `ContactAttachmentTypesSection.tsx` on
  `app/(protected)/user-management/contacts/[id]/page.tsx`.

## Design

### Data: one table, three tiers

```
stock_visibility_policies
  id                 uuid PK
  contact_id         text NULL  FK respond_contacts.id ON DELETE CASCADE
  access_type_code   varchar(50) NULL FK contact_access_types.code ON UPDATE CASCADE ON DELETE CASCADE
  mode               varchar(20) NOT NULL  CHECK (mode IN ('detailed','compact','availability'))
  warehouse_ids      uuid[] NULL          -- NULL = every active warehouse; [] = none
  created_at / updated_at

  CHECK (contact_id IS NULL OR access_type_code IS NULL)   -- a row is exactly one tier
  UNIQUE (contact_id)         WHERE contact_id IS NOT NULL
  UNIQUE (access_type_code)   WHERE access_type_code IS NOT NULL
  UNIQUE ((true))             WHERE contact_id IS NULL AND access_type_code IS NULL   -- one default row
```

Same partial-unique trick as `agent_field_access` (Postgres NULLs are distinct; one plain UNIQUE
would let a second default row in). `warehouse_ids` is an array not an M2M: the list is short,
read-only at query time, and the admin PUT replaces it wholesale. (Two-writer risk: none, only the
admin card writes it.)

**Seed (inert on deploy):** one default row `mode='detailed', warehouse_ids=NULL`. Nothing changes
for anyone until an admin adds a row. A `dealer` access-type row (`availability`, dealer-pool
warehouse ids) is **not** seeded; it is created from the admin UI when the dealer roll-out is
decided, so this PR cannot change what any existing dealer sees.

**Resolution** (`app/services/stock_visibility.py::resolve_policy(db, contact_id, space_id) -> Policy`):

1. Resolve the contact with `field_access.resolve_contact_id` (existing).
2. Row where `contact_id = <id>` -> use it.
3. Else rows where `access_type_code IN (contact's access type codes)`. If more than one matches,
   **most restrictive wins**: mode order `availability > compact > detailed`, warehouses =
   intersection. (A contact tagged `dealer` + `end_user` must not be widened by the looser type.)
4. Else the default row.
5. Contact params present but contact unresolvable -> same fail-closed behaviour as company
   scope today: zero rows. No contact params (staff web UI, n8n legacy callers without ids) ->
   default row.

`Policy = {mode, warehouse_ids: set[uuid] | None, source: 'contact'|'access_type'|'default'}`.

### Enforcement: backend `GET /inventory/stock/balance`

New query params: `requested_qty: int | None` (contact params already arrive via the global
resolver but the route reads them explicitly too, same as `/incoming-stock/list`).

Apply the policy **after** company scope, **before** serialisation, inside `StockService.list_stock`:

| mode | Rows returned | Extra block on the `ListResponse` |
|---|---|---|
| `detailed` | as today, `AND Stock.warehouse_id IN policy.warehouse_ids` when not NULL | `stock_visibility: {mode, warehouse_codes, source}` |
| `compact` | **no `data` rows** (`data: []`, `total: 0`) | `stock_visibility` + `stock_summary: [{product_id, product_code, product_name, total_on_hand, locations: [{warehouse_code, quantity_on_hand}], flags: {discontinued}}]` grouped per product over allowed warehouses, locations ordered by warehouse_code |
| `availability` | **no `data` rows** | `stock_visibility` + `stock_availability: [{product_id, product_code, product_name, needs_quantity: bool, requested_qty, available: bool|null}]`. `needs_quantity=true, available=null` when `requested_qty` is absent; else `available = sum(on_hand over allowed) >= requested_qty`. **No quantity field of any kind on this block.** |

**Every product NAMED in the request gets an entry**, including one with no stock row in any
allowed warehouse (`total_on_hand: 0` / `available: false`, or `needs_quantity` when no quantity
was given). Grouping only over the rows that came back drops it, and the absence is unreadable:
"none left" and "I never found your product" arrive as the same silence, which is exactly the
question a dealer asks. An id that names no product at all is still dropped (AC-B13).

Why empty `data` rather than stripped rows: a row with the quantity removed still tells you the
location list and count; the raw non-render shape is readable by the dead n8n AI-agent branch and
by any direct MCP caller. Empty is the only shape that cannot leak.

`last_updated_at` semantics unchanged (system-wide latest BULK_IMPORT ledger timestamp); the
compact and availability blocks carry the same value so n8n's footer keeps working.

Staff web UI (`/inventory/stock`) calls the same route with no contact params -> default row ->
unchanged today. If the default is later flipped to `compact` for the chatbot, the web grid would
break; guard: **the policy is applied only when the request carries `contact_id`** (the chatbot
path). Staff always get `detailed`, all warehouses their RBAC allows. Stated in the route docstring
and asserted by a test.

### MCP

- Catalog: add `requested_qty` to `crm_inventory_stock_balance_list` query params; docstring gains
  the availability sentence so the planner passes the number when the user gave one.
- Presenter `_stock()` branches on `stock_visibility.mode` from the raw response:
  - `detailed` -> existing `result_type: "stock"` envelope, unchanged.
  - `compact` -> `result_type: "stock_compact"`, one item per product:
    `title = product_code`, `fields = [{label:"Total", value}, {label:"BRW", value}, ...]`,
    flags passthrough, intro "Stock summary for the requested products."
  - `availability` -> `result_type: "stock_availability"`, one item per product with
    `fields = []` and `flags: {needs_quantity, available}`; intro chosen by state:
    needs_quantity -> "How many units do you need?"; available -> "Yes, we have stock."; not ->
    "Sorry, we do not have enough stock for that quantity."
- `stock_visibility` passes through on the envelope (same as `field_access`, `lookup_companies`)
  so n8n can branch without re-deriving.
- **The three blocks sit out the stock sanitizers** (`_STOCK_POLICY_BLOCK_KEYS` in `server.py`:
  popped before `_strip_stock_hidden_fields` / `_relabel_warehouse_keys` /
  `_slim_stock_nested_warehouse`, restored verbatim). Found in S3, and not optional:
  `_STOCK_HIDDEN_FIELDS` contains `available`, which on a stock ROW means quantity_available but
  on the availability block is the ENTIRE answer, so the recursive strip deleted every dealer's
  reply. The Sage relabel would likewise rename `warehouse_code` to `system_location` inside each
  summary location, where that key is the label the reader sees. Row sanitization is unchanged.
- Vocabulary: the compact block's labels are the `warehouse_code` VALUES (`BRW`, `BRW-BB`) - the
  "system location" the user asked for. The presenter also reads `system_location` as a fallback
  so a future relabel cannot silently blank the labels.
- `last_updated_at` joins `_MALAYSIA_TIME_KEYS`. It is a payload-level stamp, and the summary
  modes carry no rows, so untouched it would have made n8n's footer read 8 hours early for
  exactly the contacts on the new formats.

### n8n (three edits, promoted only on the user's call)

1. `sub-get-results` / `entity-ids-transformer`: `out.requested_qty = semantic_input?.demand_qty ?? null`.
2. `sub-get-results` / `output-structurer`: branch on `e.result_type`:
   - `stock_compact`: per item `\`${title}\nTotal: ${total}\n${loc}: ${qty}...\`` (plain, no bold,
     per the user's sample), blank line between products, existing footer.
   - `stock_availability`: emit `e.intro` only (+ product code when several), no field lines.
3. Main workflow (`txiPzSxy3Pclsz6v`): when the reply carries `stock_visibility.mode ==
   'availability'` and any item has `needs_quantity`, write
   `session_vars.pending = {intent: "check_stock", product_ids: [...], asked_at}` through
   `PUT /external/conversation-variables/{id}` in the same place `compile-current-state` persists
   turn state. On the next turn the reformulator already reads session vars; a bare number with
   `pending.intent == check_stock` becomes `demand_qty` + the pending `product_ids`, and `pending`
   is cleared after the answer. Exact node placement decided in the n8n plan-build-test-promote
   loop (see `feedback_n8n_plan_build_test_promote`), not here.

### Admin UI

**One component, three surfaces** (settled in S1): `components/stock-visibility/StockVisibilitySection.tsx`
takes a `scope` prop (`contact` / `access_type` / `default`) rather than the three copies the
name `ContactStockVisibilitySection` implied. It shows the **effective** policy with its source
badge (`Contact override` / `Access type: <name>` / `Default`), a mode `SearchableSelect`
(Detailed / Compact / Availability only), a warehouse `SearchableMultiSelect` (server-search,
`/inventory/warehouses`, empty = all), a "Dealer pool" preset button that fills
`segment='dealer'` warehouses, and Save / Remove override (Remove = hard delete +
`ConfirmDeleteDialog`). Save on an inheriting tier is what creates that tier's row.

- Contact detail page (`user-management/contacts/[id]`): rendered full width at the foot of the
  Contact Information grid, beside Companies / Attachment types. Full width because the two
  pickers clip their chips inside a half-width grid cell at 375px.
- Access type management page (`user-management/contact-access-types`): a row action on the
  existing grid opens the card in a dialog for that access type. Not a card per row and not a
  column: the API has no list endpoint, and one GET per access type on page load would be N
  requests for a value that is read rarely.
- System settings: a new `Stock Visibility` tab (`user-management/settings/stock-visibility`)
  holding the default row.
- No explanations in-UI (Outline guide instead). No UUIDs shown; warehouses render as `code - name`.
- **Empty Locations = all locations** (stored `warehouse_ids` NULL). The `[]` reading ("no stock
  at all") is not reachable from the S1 UI, which is deliberate: it only becomes an operator
  action in the later pass that retires the Respond `is_allowed_stock` field (roll-out step 5).

### API

```
GET    /api/v1/inventory/stock-visibility/effective?contact_id=&space_id=   -> Policy + source   (external, n8n preflight convenience)
GET    /api/v1/inventory/stock-visibility/contacts/{contact_id}             -> effective + override row | null
PUT    /api/v1/inventory/stock-visibility/contacts/{contact_id}             -> upsert override {mode, warehouse_ids}
DELETE /api/v1/inventory/stock-visibility/contacts/{contact_id}             -> drop override
GET|PUT|DELETE /api/v1/inventory/stock-visibility/access-types/{code}
GET|PUT        /api/v1/inventory/stock-visibility/default
```

Plus one filter on an existing route, for the "Dealer pool" preset (the only caller):

```
GET /api/v1/inventory/warehouses?segment=dealer&is_active=true   -> new `segment` query filter
```

`warehouses.segment` and `WarehouseResponse.segment` already exist; S2 adds the filter. The
Locations picker itself needs nothing new - it server-searches the same route with `query=`.

Every policy route returns the same body: `{effective: Policy, override: Policy | null}`, where
`Policy = {mode, warehouses: [{id, code, name}] | null, source, source_label}`. Warehouses come
back RESOLVED, not as bare ids, so the UI renders `CODE - name` without a second round trip and
without a UUID on screen. `override` is null when the tier inherits; DELETE returns the tier the
caller falls back to. The full contract, request and response, is documented at the top of
`sorento_crm_frontend/services/stockVisibilityService.ts`.

Permission: reuse `inventory.stock.edit` for writes, `inventory.stock.view` for reads (no new slug;
gating map entry added per `project_permission_gating_all_routes`). `response_model` declares every
block (`stock_visibility`, `stock_summary`, `stock_availability`) or they are silently dropped.

## Roll-out (A/B -> phase-out)

1. Deploy. Default row = `detailed`, no overrides. Zero visible change.
2. Admin adds a contact override `compact` for the requesting user. Observe.
3. Add more contact overrides, or flip the default row to `compact` and delete the overrides.
   Phase-out of the legacy format = one UPDATE on the default row.
4. Dealer onboarding: one `dealer` access-type row (`availability`, dealer pool). Every contact
   tagged `dealer` inherits it; no per-dealer rows.
5. Respond custom field `is_allowed_stock` becomes redundant (`warehouse_ids = []` on a contact
   = no stock at all). Retire it in a later n8n pass, not here.

## Slices

| # | Slice | Phase | Notes |
|---|---|---|---|
| S0 | Plan + UAC (this file) | - | done |
| S1 | FE mock: `StockVisibilitySection` against a mocked service, three states, 375 / 1280 | Phase 1 | done (browser run deferred to S6) |
| S2 | Backend: migration + model + `stock_visibility.py` resolver + enforcement in `list_stock` + CRUD routes; pytest first (resolution tiers, most-restrictive merge, fail-closed, empty `data` in compact/availability, staff path untouched, `response_model` fields present) | Phase 2 | done - `tests/test_stock_visibility_policy.py`, 34 passed |
| S3 | MCP: catalog param + presenter branches; pytest on envelope shapes | Phase 2 | done - `sorento_crm_mcp/tests/test_presenters_stock.py` (25) + backend B13 (zero-stock products still answered). Restart the MCP session to pick it up |
| S4 | FE wiring: service + hooks + section on contact page, access-type page, settings; vitest | Phase 2 | |
| S5 | n8n: transformer + structurer + pending-quantity turn; live-envelope harness capture | separate n8n plan-build-test-promote; promote = user's call | |
| S6 | Browser verification via agent-browser from `/` by sidebar; `/code-review`; DoD gate; PR | Phase 3 | |

## Risks / non-goals

- `compact` on a product with many project bins prints many lines. Accepted; locations are the
  contact's allowed set, and the dealer pool keeps it to three.
- Binary-search leak in `availability` accepted for v1; coarse buckets are a later option.
- Per-region dealer pools: not v1. The table already supports it (per-contact `warehouse_ids`).
- Internal web AI assistant (`ai_assistant_*`, user-keyed) is out of scope; it does not serve
  contacts.
- Multi-tenant: `space_id` still hardcoded on the n8n side; the resolver already accepts it, so
  nothing here gets harder when a second workspace appears.
