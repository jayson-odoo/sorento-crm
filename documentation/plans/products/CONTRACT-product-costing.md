# CONTRACT: Product costing (lane PRODUCT-COSTING)

The one contract the tester and the coder both build against. Plan:
`PLAN-product-costing-10nov.md`; UAC: `product-costing-10nov-acceptance-criteria.md` (AC ids below);
mock: `mockups/product-costing-10nov-mockup.html`. Where this file and the UAC disagree, this file
wins and the UAC is corrected.

## 1. Enums and number rules

- `cost_method`: `primary` | `selected` | `average` | `last_po`. Labels: "Primary supplier",
  "Selected supplier", "Average of supplier prices", "Last PO price". `selected` is valid ONLY on a
  product override (never on a party profile or the company default) (AC-LC-06).
- `transport_mode`: `add` (flat MYR per unit) | `multiply` (factor).
- Percent fields (`markup_pct`, `margin_pct`) are percent numbers: 8 means 8%.
- Money and rates are computed in `Decimal` at full precision; the API returns floats rounded to
  6 dp; only the UI and the Excel display round to 2 dp half-up.
- Rates: `rate_to_base` = MYR per 1 unit (RMB 0.625). `units_per_base` = 1 / rate_to_base (RMB 1.6),
  returned rounded to 4 dp. The page's Rate column shows `units_per_base` (the workbook's 1.6).
- Formula (AC-LC-01): `landing = unit_cost * rate_to_base * sst_factor`, then `+ value` (add) or
  `* value` (multiply). MYR: rate 1. No rule: `+ 0` and reason `no_transport_rule`.
- Party: `final = landing * (1 + markup/100)`, `margin_pct = (list_price - final) / final * 100`.
- Company standard: `final = list_price`, `markup_pct = (list_price - landing) / landing * 100`
  (achieved), `markup_source = "achieved"`, `margin_pct = null`.
- `list_price` is `products.list_price` (AutoCount). NOTHING in this lane writes it or calls
  AutoCount (AC-CG-14).

## 2. Data model (one additive migration `pc_0001_product_costing`)

All tables audited (`__audit_track__ = True`). Company-scoped ones use `CompanyScopedMixin`.
Models live in `sorento_crm_backend/app/models/costing.py`, exported from `app/models/__init__.py`.

| Table | Columns | Notes |
|---|---|---|
| `exchange_rates` (NOT company-scoped, public schema) | `id` uuid pk, `currency` varchar(3), `rate_to_base` numeric(18,6) CHECK > 0, `effective_from` date NOT NULL, `note` varchar(255), `created_by` varchar(100), `created_at`, `updated_at` | UNIQUE (`currency`, `effective_from`). MYR rows refused by the service. |
| `costing_settings` | `id` uuid pk, `company_id` UNIQUE, `sst_factor` numeric(6,4) default 1.1000 CHECK > 0, `default_method` varchar(16) default `primary` CHECK in (primary, average, last_po), `updated_by`, `updated_at` | one row per company, created on first write; a read with no row returns the defaults |
| `costing_category_rules` | `category_id` pk FK `product_categories` ON DELETE CASCADE, `company_id`, `mode` varchar(8) CHECK in (add, multiply), `value` numeric(12,4) CHECK > 0, `updated_by`, `updated_at` | no row = no rule |
| `costing_product_overrides` | `product_id` pk FK `products` ON DELETE CASCADE, `company_id`, `transport_mode` nullable, `transport_value` nullable (both or neither, CHECK), `cost_method` nullable CHECK in (primary, selected, average, last_po), `cost_method_supplier_id` nullable FK `suppliers` ON DELETE SET NULL (CHECK: required when `cost_method = 'selected'`, null otherwise), `updated_by`, `updated_at` | row deleted when every field is cleared |
| `customer_costing_profiles` | `customer_id` pk FK `customers` ON DELETE CASCADE, `company_id`, `markup_pct` numeric(7,3) NOT NULL CHECK >= 0, `cost_method` nullable CHECK in (primary, average, last_po), `is_active` bool default true, `created_by`, `created_at`, `updated_at` | |
| `customer_costing_products` | `id` uuid pk, `company_id`, `customer_id` FK `customers` ON DELETE CASCADE, `product_id` FK `products` ON DELETE CASCADE, `markup_pct` numeric(7,3) nullable CHECK >= 0, `added_by`, `added_at`, `updated_at` | UNIQUE (`customer_id`, `product_id`) |

Migration also: seeds one `exchange_rates` row per `scm.currency_rate` row (`effective_from` =
`as_of`, else the migration date; `ON CONFLICT DO NOTHING`, so a rerun adds nothing); inserts
permission `products.party_costing.manage` (WHERE NOT EXISTS) and grants it BY ROLE SLUG to
`admin`, `director` only; inserts `products.cost.view` WHERE NOT EXISTS with no grants (#2319 owns
its grants). Downgrade drops exactly what upgrade added (tables, the manage permission and its
grants; not `products.cost.view`). `down_revision` = main's single head at build time.
`products.party_costing.manage` is added to `app/rbac/permission_registry.py`.

## 3. Cost basis (AC-LC-02..06)

Per product, on date `as_of` (default: today in Malaysia, `app/services/sales/agent_class_service.py:42`):

- Supplier cost of a link: `supplier_cost_service.current_cost(rows, as_of)`
  (`app/services/procurement/supplier_cost_service.py:49`: standard packaging, else the only
  packaging, else None) over the link's `product_supplier_costs`. A link with NO cost rows at all
  falls back to `product_suppliers.unit_cost` / `currency` when set. Otherwise no cost.
- Rate: the `exchange_rates` row for the currency with the latest `effective_from <= date`.
  None -> reason `no_rate` (with `currency`, `date`). MYR -> 1.
- Effective method: product override `cost_method` > party profile `cost_method` > company
  `default_method`; `cost_method_source` = `product` | `party` | `company`.
- `primary`: the link with `is_primary_supplier`; none -> `no_primary`.
- `selected`: the override's `cost_method_supplier_id` link; that supplier no longer linked
  (or null) -> `selected_not_linked`.
- `average`: mean of `landing` over every link with a cost AND a rate; each link skipped is in
  `skipped: [{supplier_code, reason}]`; none usable -> `no_cost`. `supplier_code` null.
- `last_po`: latest `purchase_order_lines` row for the product with `unit_cost` not null, not
  `removed_unreferenced`, `purchase_orders.issue_date <= as_of`, ordered `issue_date DESC,
  created_at DESC`; currency `COALESCE(line.currency, po.currency)`; converted at the rate in force
  on the PO's `issue_date`; none -> `no_po_price`. Returns `po_number`, `po_date`.
- No fallback between methods (AC-LC-05).
- Transport: product override (`transport_source = "product"`) > the product's own category rule
  (`"category"`, no parent walk) > none (`null`, + 0, reason `no_transport_rule`).

Reason codes: `no_cost`, `no_rate`, `no_primary`, `selected_not_linked`, `no_po_price`,
`no_transport_rule`. UI text: "No cost", "No rate for {CUR} on {d MMM yyyy}", "Set a primary
supplier", "Selected supplier no longer linked", "No PO price", "No transport rule".

## 4. API (`/api/v1/master-data/costing`, router `app/api/v1/master_data/costing.py`)

Gates: every GET needs `products.cost.view` via `require_permission` (`app/dependencies.py:473`,
staff session only; admin / superadmin bypass). Every costing write needs
`products.party_costing.manage` AND `products.cost.view`. Exchange-rate writes need
`scm.config.manage` AND `products.cost.view`. A bare `X-API-Key` caller and a contact session get
401/403. No route under this router contains `import` (AC-CG-10).

### 4.1 `GET /rows`

Query: `party_id` (customer id, optional), `q`, `category_id` / `brand_id` / `cost_method`
(comma-separated multi), `has_cost` (`true` narrows to rows with a landing; absent or `false` =
no narrowing; there is NO default filter), `as_of` (YYYY-MM-DD), `page` (1), `limit` (50, max
500), `sort` (`product_code` default | `category_name` | `landing` | `final` | `markup_pct` |
`margin_pct`), `dir` (`asc` | `desc`).

Company standard (no `party_id`): every product, inactive included (AC-CG-03). Party view: only
that party's `customer_costing_products`.

```json
{
  "data": [Row], "total": 1, "page": 1, "limit": 50, "as_of": "2026-11-11",
  "view": "standard" | "party",
  "party": null | Party,
  "settings": {"sst_factor": 1.1, "default_method": "primary"}
}
```

`Row`:
`product_id, product_code, product_name, category_id, category_name, brand_id, brand_name,
list_price, supplier_id, supplier_code, currency, unit_cost, rate_to_base, units_per_base,
rate_effective_from, sst_factor, transport_mode, transport_value, transport_source, landing,
cost_method, cost_method_source, cost_method_supplier_id, markup_pct, markup_source
("row" | "party" | "achieved"), final, margin_pct, po_number, po_date, reasons: [{code, currency?,
date?}], skipped: [{supplier_code, reason}], party_product_id` (party view: the
`customer_costing_products.id`, else null). Unknown numbers are `null`, never 0.

`Party`: `customer_id, customer_code, customer_name, has_profile, markup_pct, cost_method,
is_active, product_count`. A customer with no profile: `has_profile: false`, `data: []`.

### 4.2 `GET /rows/{product_id}/suppliers?party_id&as_of`

`{"data": [{supplier_id, supplier_code, supplier_name, is_primary, lead_time_days, currency,
unit_cost, landing, final, markup_pct, margin_pct, reasons}]}`. Party view: `final` at the row's
mark-up and `margin_pct` vs list price. Standard: `final = list_price`, `markup_pct` achieved,
`margin_pct` null.

### 4.3 `PATCH /rows` (manage)

```json
{"party_id": "cust-uuid" | null,
 "changes": [{"product_id": "p", "markup_pct": 10,
              "transport_mode": "add", "transport_value": 8,
              "cost_method": "selected", "cost_method_supplier_id": "s"}]}
```

Only keys present are changed; `null` clears (mark-up -> party's; transport -> category rule; method
-> party / company). Pydantic `extra="forbid"`: any other key (`unit_cost`, `rate`, `sst_factor`,
`list_price` ...) -> 422. `markup_pct` without `party_id`, or for a product not on the party ->
422. `transport_mode` and `transport_value` together (both set, `value > 0`, or both null).
`selected` needs a `cost_method_supplier_id` that is a current link of the product. All or nothing:
one invalid change -> 422 and nothing written. Response `{"updated": <changed cells>}`. Each changed
cell is one audited row change (old -> new).

### 4.4 `GET /rows/{product_id}/history?party_id`

`{"data": [{changed_at, user_name, field, old, new}]}` newest first: audit rows of that product's
`costing_product_overrides` row and (with `party_id`) that party's `customer_costing_products` row.
Nothing from other rows.

### 4.5 `GET /export` (same query as 4.1 minus paging)

`.xlsx`. Row 1: `Costing - <Company standard | CODE NAME> - as of <d MMM yyyy>`. Row 2 headers, in
this order: Category, Code, Name, Supplier, Currency, Cost, Rate (per MYR), SST, Transport mode,
Transport value, Landing (RM), Cost method, Mark-up %, Final (RM), List price (AutoCount), Margin %,
Note. Numeric cells are numbers; unknown = empty cell; Note = the reason texts joined by "; ".

### 4.6 Settings

- `GET /settings` -> `{sst_factor, default_method}` (defaults 1.1 / primary). `PUT /settings`
  (manage) same body; `sst_factor > 0`; `default_method` in (primary, average, last_po).
- `GET /category-rules` -> `{"data": [{category_id, category_name, mode, value}]}` every category,
  `mode`/`value` null without a rule. `PUT /category-rules/{category_id}` (manage)
  `{mode, value}`; both null clears.
- `GET /exchange-rates?currency` -> `{"data": [{id, currency, rate_to_base, units_per_base,
  effective_from, note, status}]}`, newest first per currency, `status` = `scheduled` (future) |
  `in_force` | `past` relative to today.
- `POST /exchange-rates` (`scm.config.manage`) `{currency, effective_from, rate_to_base?,
  units_per_base?, note?}`: exactly one of the two rate fields; `units_per_base` 1.6 stores
  0.625000. Same currency + date -> 409. Rate <= 0 or MYR -> 422.
- `PUT /exchange-rates/{id}` `{rate_to_base? | units_per_base?, note?}`.
- Delete: deferred record action `exchange_rate.delete` (`app/services/record_actions.py`,
  `FormAction`, `WINDOW_DESTRUCTIVE`, permission `scm.config.manage`).

### 4.7 Parties

- `GET /parties/{customer_id}` -> `Party`.
- `PUT /parties/{customer_id}` (manage) `{markup_pct, cost_method (null|primary|average|last_po),
  is_active}` upsert -> `Party`.
- `POST /parties/{customer_id}/products` (manage) `{product_ids: [...]}` max 500 (501 -> 422);
  no profile -> 404; duplicates are a no-op -> `{added, already}`.
- Remove: deferred record action `costing_party_product.unlink` (entity type
  `costing_party_product`, entity id = `customer_costing_products.id`, `WINDOW_REVERSIBLE`,
  permission `products.party_costing.manage`).

### 4.8 Existing code that changes

- `app/services/scm/money.py` `load_rates` (line 99) reads the `exchange_rates` row in force
  TODAY per currency; `Rate.as_of` = its `effective_from` (AC-ER-04).
- `app/services/scm/currency_rate_service.py`: `list_rates` returns the in-force rows; `upsert_rate`
  writes the `exchange_rates` row at `effective_from = as_of or today` (update on the same date);
  `delete_rate(currency)` deletes the in-force row. The existing SCM routes and their tests keep
  their shapes.
- `app/services/customer_merge.py` `_merge_group` unique-collision step (beside
  `respond_contact_customers` / `customer_item_code_map`, around line 657-706): survivor has a
  profile -> the retired profile row is dropped via `_drop_where`; retired
  `customer_costing_products` whose `product_id` the survivor already has are dropped the same way;
  the rest are repointed by the generic FK move (AC-PC-10).

## 5. Frontend

Route `app/(protected)/master-data-management/costing/page.tsx` renders `CostingView`. Files under
that folder: `components/CostingView.tsx`, `components/CostingSettingsDialog.tsx`,
`components/AddCostingProductsDialog.tsx`, `services/costingService.ts` (via `lib/api-client`,
`extractApiError`), `hooks/useCosting.ts`, `types/costing.types.ts`. Menu: a "Costing" child under
Products (`config/menu.config.tsx:583`), `path: '/master-data-management/costing'`,
`permission: 'products.cost.view'`.

Page (AC-CG): `PageHeader` title "Costing"; header actions "Settings" and the ONE primary "Edit"
(only with `products.party_costing.manage`); in edit the header shows "Cancel" and "Save".
Party picker (`CustomerDebtorCombobox` with `pickOnly`, placeholder "Company standard",
clearable) above the grid, URL param `party`. Chips beside it in party view: "Party mark-up",
"Cost method", "Rates as of", "Products". `DataGrid` + `DataGridListToolbar` like
`sales/targets/components/SalesTargetsView.tsx:439-537`: search; custom Filters popover (Category,
Brand, Cost method multi-selects and a "Has cost" switch, OFF by default; URL params
`category`, `brand`, `method`, `has_cost=1`, `as_of`); Columns; `exportConfig={false}` plus a
secondary action "Export" that downloads `GET /export` with the current params; secondary action
"Add products" in party view (manage). `tableLayout: { width: 'fixed', columnsResizable: true }`,
`columnResizeMode: 'onChange'`, explicit `size`, `listingKey` `products.cost.view::costing`.

Column headers, exactly and in this order: "Category", "Code", "Name", "Supplier", "Cost", "Rate",
"SST", "Transport", "Landing (RM)", "Cost method", "Mark-up", "Final (RM)", "List price
(AutoCount)", "Margin" ("Margin" only in party view). Cost shows `{CUR} {amount}`; Rate shows
`units_per_base`; Transport "+ RM 8.00" or "x 1.07"; unknown shows the reason pill text, never
"0.00". A value set on the row (transport_source product, cost_method_source product,
markup_source row) shows a marker with title "Set on this row".

Row expand: supplier sub-grid with headers "Supplier", "Primary", "Lead time", "Cost", "Landing
(RM)", "Final (RM)", "Margin if bought here" (standard view: "Mark-up if bought here").

Edit (AC-CG-08), as `TargetRecord.tsx:536-551`: inputs replace values in the same cells; labels
`Mark-up for {code}` (NumberInput; party view only), `Transport for {code}` (SearchableSelect:
Category rule / Add / Multiply, clearable) + `Transport value for {code}` (NumberInput), `Cost
method for {code}` (SearchableSelect, clearable to "Company default", options include Selected
supplier which then shows `Supplier for {code}`). Transport and method inputs show the hint
"applies to every party". Landing, Final and Margin recompute from the draft while typing (same
formula as section 1, in `lib`-free TS inside the feature folder). Save sends ONE
`PATCH /rows` with only changed cells; success exits edit and toasts; failure keeps edit open and
the typed values. Cancel discards.

Row menu: "History" opens `AuditTrail`-style list from `GET /rows/{id}/history`; "Remove from
party" (party view, manage) is a `DeferredActionButton` on `costing_party_product.unlink`.

Settings dialog (AC-CG-13): `FormDialogScaffold`, line tabs "Exchange rates", "SST and method",
"Transport by category". Rates: rows with Currency, Effective from, Units per MYR 1, MYR per unit,
Status ("Scheduled" / "In force" / "Past"), Note; "Add rate" form takes Currency, Effective from
and the rate as "Units per MYR 1" (default) or "MYR per unit"; delete is a `DeferredActionButton`
(`exchange_rate.delete`), no confirm.

Add products dialog: `useProductTargetPicker` (`products/[id]/components/ProductTargetPicker.tsx`)
with `sourceProductId` made optional; already-added products are marked and not re-sent.
