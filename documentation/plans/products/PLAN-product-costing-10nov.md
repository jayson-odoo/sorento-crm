# PLAN: Product costing - Purchasing vs Pricing tabs + party costing (Bath Plus, dealers)

Status: Plan v5 (owner 11 Nov 00:2x: one costing page = the workbook in the system, Sales > Targets pattern); mock v5 + questions QA-QE on PR #2321; build after owner approval. Track: full (migration + new permission + cost gating).

Lane: PRODUCT-COSTING. Source: owner + management meeting 9 Nov 2026 "Project Internal Costing",
owner's workbook Internal_Costing_Formula.xls (numbers are the owner's draft). Depends on
SUPPLIER-COST-ACCESS (PR #2319, open draft) for the `products.cost.view` permission.

## 0. v5: one costing page (owner, 11 Nov 00:2x)

Owner (gist): "the end objective is a place for the user to see all the costing related to the
Excel sheet I gave you. Make the mockup simpler and reuse more components, then also a page for
the user to see the costing and decide what to do with it ... deliver the Excel sheet in the
system, just like how we delivered for sales target."

How Sales > Targets was delivered (measured): the list page `app/(protected)/sales/targets/components/SalesTargetsView.tsx:439-537`
is a `DataGrid` + `DataGridListToolbar` (search, Filters popover, Columns, Export
`exportConfig`, secondary action "Import from Excel") + `DataGridTable` + `DataGridPagination` in a
`Card`, fixed resizable columns, `listingKey`; the Excel import is
`sales/targets/components/DealerTargetImportDialog.tsx` (FileDropzone, Test writes nothing, Import
only after a Test of the same file, per-row report with CountTiles) over
`app/services/sales/dealer_target_import.py` (pure parse + dry run in a rolled-back savepoint) and
`app/api/v1/sales/targets.py:209-226` (template + import routes); figures are edited in place with
an Edit / Save mode (`TargetRecord.tsx` `TeamFigures` / `FigureInput`, NumberInput in table cells).
There is no generic inline-edit grid in the repo; cell inputs elsewhere use `LiveNumberInput`
(`components/ui/number-input.tsx`, e.g. `scm/components/SupplierSheet.tsx`). Sales targets has no
History panel; history elsewhere is `components/audit/AuditTrail.tsx`.

v5 therefore centres the lane on ONE page, **Products > Costing** (UAC section CG): Sheet1's
columns left to right, a party picker (Company standard by default, or a customer such as Bath
Plus 304-R017), a row expand for per-supplier margin, Edit / Save in place on mark-up / transport /
cost method, Excel export and Test-then-Import, row History, and a Settings dialog (dated rates,
SST + default method, transport by category). Dropped because the page covers them: the product
Pricing tab, the Purchasing tab extension, the customer Costing tab, the Party costing index and
the separate settings page. Kept: rules (section 3), rates (3.1), methods (3.2), party on
`customers` with profile tables (3.3 data model, plus a nullable per-row mark-up on the party's
product row, needed for inline mark-up edits), Bath Plus = 304-R017, management-only, no AutoCount
write-back.

## 1. What exists today (measured, file:line)

The brief says "the system only knows unit cost as last purchase price from POs". That is out of
date: three cost sources already ship.

| Data | Where | Notes |
|---|---|---|
| Product-supplier link: supplier, primary flag, lead time, MOQ, unit cost, currency | `product_suppliers`, `sorento_crm_backend/app/models/procurement.py:96-122` | `unit_cost`/`currency` are kept equal to the cost row in force by the cost writer |
| Dated supplier cost rows per link (per packaging), cost-list uploads + verification | `product_supplier_costs`, `app/models/cost_price.py:52-95`; `price_in_force` `app/services/procurement/supplier_cost_service.py:72`; routes `app/api/v1/procurement/product_suppliers.py:128,194-219` | lane #1288; this is the "cost at product-supplier level" the meeting asked for |
| Product `cost_price`, `list_price`, `invoice_price`, `currency` (MYR) | `app/models/product.py:333-336` | `list_price` and `cost_price` are written by the AutoCount master sync, `app/services/master_ingest_service.py:656-660` |
| Last PO cost (supplier, currency, PO no.) | `app/services/product_purchase_history_service.py:44,114` | shown on product Overview as "Last purchase price" |
| Currency rates (one current rate per currency, to MYR, `as_of`, no history) | `scm.currency_rate`, `app/models/scm.py:1660-1688`; `app/services/scm/money.py:28` (`BASE_CURRENCY = "MYR"`), `app/services/scm/currency_rate_service.py` | used by SCM planning; RMB at 1.6 per MYR = `rate_to_base` 0.625 |
| Price floors (percent of list or absolute, per product / category / system) | `price_floor_rules`, `app/models/projects.py:1106-1140` | percent-of-list, so unaffected by a cost basis |
| Dealer cost from list price on promotions | `dealer_cost_and_margin_from_list`, `app/services/marketing_service.py:289-303`; `promotion_products.dealer_discount_percent` `app/models/marketing.py:189` | per promotion line, not a product field; no "25% dealer margin" constant exists in code |
| Product detail tabs | `sorento_crm_frontend/app/(protected)/master-data-management/products/[id]/components/ProductDetail.tsx:314-355`; Suppliers tab `ProductSuppliersTab.tsx`, Purchases tab `ProductPurchaseHistoryTab.tsx`; Overview cost/invoice/last purchase price `ProductDetail.tsx:413-470` | Suppliers tab gated on `procurement.product_suppliers.view` (`ProductDetail.tsx:85`) |
| Cost permission | PR #2319 adds `products.cost.view` (purchasing + management + admin) | not merged yet |

What does NOT exist: SST factor, transport rule (add or multiply) per category or product, a
costing mark-up, landing cost, any "B Plus" company/list (repo grep: no hit), a costing export.

## 2. Owner answers (10 Nov, 23:3x)

- Q1 rate: a STANDARD ERP exchange-rate table (currency, rate, effective from, history; the rate
  used is the one in force on the date; audited). Reuse/extend `scm.currency_rate` if it fits.
  SST = one company setting. Transport per category with per-product override: confirmed.
- Q2 (a): achieved mark-up, read-only.
- Q3 (a): AutoCount `list_price` is the selling price. NEVER write a selling price back to AutoCount.
- Q4: cost basis is a selectable METHOD (primary supplier, selected supplier, average, last PO
  price). Default primary supplier (last PO fluctuates). Company default + per-product override;
  the method used is shown next to the cost.
- Q5: "B Plus" = **Bath Plus** (workbook "Bath+ cost price"; AutoCount company DB `AED_BATHPLUS`).
  Owner 23:4x: design for many partners, not one case. Owner 23:5x (verbatim): "For the costing, it
  is not just like business partner. It is a PARTY. Dealer also can have their own costing." So no
  `business_partners` table: costing attaches to the existing party record (section 3.3). Any party
  (dealer, Bath Plus, later others) can have a costing profile.
- Q6 (a) product > party > company default, and Q7 (a) party headroom margin: crew took the
  recommendations as working answers (23:5x).

## 3. Rules

- Landing cost (MYR) = supplier unit cost x rate (MYR per unit, in force on the date) x SST, then
  transport (category rule, or the product's override):
  - ADD (ceramics, WCs, jacuzzi): + flat MYR per unit (e.g. 8).
  - MULTIPLY (accessories, sinks, taps, hose, valves, shower): x 1.07; kitchen sinks x 1.1.
- Party price = landing cost x (1 + that party's costing mark-up); Bath Plus 8%.
- Party margin at standard selling price = (selling - party price) / party price (Q7 a).
- Selling price = AutoCount `list_price`, read-only, standard per product, never written back.
- Purchasing tab, per supplier: mark-up if bought here = (selling - that supplier's landing) /
  that landing, all MYR.
- Pricing tab: cost basis by the product's METHOD; achieved mark-up = (selling - basis) / basis.
- Cost needs `products.cost.view` (#2319); dealers never see cost.
- Full precision internally; 2 dp half-up at display/export only. An unknown cost is never 0.

### 3.1 Exchange rates (Q1): extend, do not replace

`scm.currency_rate` (`app/models/scm.py:1660`) holds ONE current rate per currency, history
"deliberately absent" (its docstring), read by the SCM planner through `load_rates`
(`app/services/scm/money.py:99`, used by `reorder_engine.py:848`, `reorder_run_service.py:737,1748,3119`).
It does not fit a dated table on its own, so:

- New table `exchange_rates`: `currency`, `rate_to_base` (MYR per 1 unit, Numeric(18,6), same
  direction as today), `effective_from` (date, required), `note`, `created_by`, timestamps;
  unique (`currency`, `effective_from`); `rate_to_base > 0`; `__audit_track__ = True`. Group-wide,
  not company-scoped, like `scm.currency_rate` today (every party's costs come from Sorento's own suppliers).
- Rate in force on date D = the row with the latest `effective_from <= D`. None -> "No rate for X
  on D", never 1. MYR is 1 by definition and has no row.
- One source of truth: `load_rates` (`money.py:99`, the single read the planner uses) reads the
  `exchange_rates` row in force TODAY instead of `scm.currency_rate`; its `Rate.as_of` becomes that
  row's `effective_from`, so every planner screen keeps its "as of" label. A future-dated rate takes
  effect on its day with no job. The migration seeds one `exchange_rates` row per existing
  `scm.currency_rate` row (`effective_from` = its `as_of`, else the migration date) and leaves the
  old table in place, no longer written (additive only; dropped by a later cleanup lane).
- Screen: the existing SCM Currency rates panel
  (`app/(protected)/scm/policies/components/CurrencyRatesPanel.tsx`) becomes a dated list per
  currency (add rate with effective date; edit/delete a row, delete = deferred action). It shows
  both directions: "1 RMB = 0.625000 MYR (1 MYR = 1.6000 RMB)", and accepts entry as "MYR 1 = x RMB"
  since that is how the workbook states it.
- Which date: supplier price-list costs are converted at the costing date (today by default; the
  party costing list has an "As of" date). A last-PO cost is converted at the rate in force on the PO's
  issue date.

### 3.2 Cost basis method (Q4)

| Method | Cost basis | Notes |
|---|---|---|
| Primary supplier (company default) | the primary link's supplier cost in force on the date | "Set a primary supplier" when none |
| Selected supplier | a chosen link's cost in force | the product override names the supplier; supplier removed -> "Selected supplier no longer linked" |
| Average of supplier prices (proposed average) | simple mean of the landing costs of every linked supplier with a cost AND a rate on the date | stable (moves only when a price list or rate changes), no PO needed; suppliers skipped for no cost/no rate are named. Rejected alternative: quantity-weighted average of PO lines over 12 months, which moves with every order, the fluctuation the owner wants to avoid |
| Last PO price | the latest PO line unit cost (`product_purchase_history_service.py:114`) converted at the PO-date rate | shows PO no. and date |

- Company default = a setting (Primary supplier). Product override = method (+ supplier for
  Selected supplier), clearable back to "Company default".
- No silent fallback: a method that yields nothing shows "No cost (method: X)".
- The method is shown next to every cost: Pricing tab ("Primary supplier, SUP-A01"), party
  costing grid column "Cost method", export column "Cost method".
- Precedence (Q6 a): product override > party override > company default.

### 3.3 Party costing (Q5, owner 23:5x)

**What "party" is today (measured).** There is no single party model above `customers`. Two
records hold organisations:

| Record | What it is | Typing | Who is in it |
|---|---|---|---|
| `customers` (`app/models/order.py:77`) | the debtor / buying ledger, fed by the AutoCount customers push, the order import and the customer form | `customer_type` company/individual (`order.py:152`); CRM `debtor_type` project / project_cash / cash_sales (`order.py:186`, `app/services/debtor_type.py:12`); AutoCount `autocount_debtor_type` (`order.py:190`); `customer_group_id` (`order.py:196`, `customer_groups` `order.py:51`) | every dealer and every organisation that buys from Sorento |
| `projects.parties` (`app/models/projects.py:97-137`) | organisations on projects, reusable across projects | `party_type` = the party's usual project role from the editable lookup `project_party_role` (developer, architect, main contractor, trading house, subcontractor, tender party, consultant, interior designer; `app/services/project_party_roles.py:30-39`) | architects, developers, contractors; "Architects never buy, which is exactly why they must not live in customers" (its docstring). `customer_id` bridges to `customers` once a party buys |

How dealers are told apart today: not on `customers`. Dealer-ness is a contact access type
(`contact_access_types`: `dealer`, `sorento_dealer`, `end_user`; `app/models/access.py:67`) on
WhatsApp contacts (`respond_contacts`), linked to their debtor through `respond_contact_customers`
(`access.py:11`). Project customers are `debtor_type` project / project_cash. Partners have no type.

**Recommendation (Q8 a): the costing party is the `customers` row.** Costing produces a price a
party BUYS at, and every party that buys from Sorento (dealer, Bath Plus, a trading house that has
ordered) is a debtor. A `projects.parties` row reaches costing through its existing `customer_id`;
an architect never buys, so it never needs a costing profile. Putting costing on `projects.parties`
instead would mean creating party rows for every dealer and adding "dealer" / "partner" to the
project role list the registration form shows. No party type is added for costing: the costing
lists show the existing AutoCount debtor type and customer group, and a type is added only when a
costing rule first differs by type (named trigger).

**Tables (company-scoped, `__audit_track__ = True`):**

- `customer_costing_profiles`: `customer_id` (PK, FK `customers` ON DELETE CASCADE), `markup_pct`
  (required, >= 0), `cost_method_override` (nullable: primary / average / last PO), `is_active`,
  `created_by`, timestamps. A separate table, not columns on `customers`, on evidence: dealer-facing
  and broad surfaces read `customers` today (portal orders `app/api/v1/public/portal.py:663`,
  customer list/export, MCP), so a cost-shaped column there is one serializer away from a dealer.
  A separate table is reachable only through the costing endpoints, all gated on
  `products.cost.view`.
- `customer_costing_products`: `customer_id`, `product_id`, `added_by`, `added_at`; unique pair.
- Customer merge (`app/services/customer_merge.py`) moves every FK onto `customers.id` read from
  `pg_constraint`, so both tables follow a merged debtor with no extra code; a test pins it (both
  survivor and retired have a profile -> survivor's kept, retired's product rows unioned, logged).

**Bath Plus as a party (Q9).** (a) If Bath Plus is already a debtor (Sorento sells to it, so the
AutoCount push would have brought it in), pick that row; crew can check on the dev copy:
`SELECT customer_code, customer_name, debtor_type, autocount_debtor_type FROM customers WHERE
customer_name ILIKE '%bath%plus%' OR customer_name ILIKE '%bath+%';`. (b) If it is not, staff create
it with the existing Customers > New form (`app/(protected)/order-management/customers/new`) using
the debtor code AutoCount AED_SORENTO will give it; when the AutoCount push later sends that debtor,
the code-unique merge folds the two rows into one, carrying the costing profile. No seed row:
a migration cannot know Bath Plus's debtor code. Its costing profile (8%) is created from its
customer page.

**Screens:**

- Customer detail gets a **Costing** tab (same permission-gated tab pattern as Branches / Billing,
  `app/(protected)/order-management/customers/components/CustomerDetail.tsx:31-49`), shown only with
  `products.cost.view`; view and edit share it. No profile: empty state + header CTA "Set up
  costing". With a profile: metadata (mark-up, method) under the header, then the party costing
  list: Code, Name, Category, Cost method (+ source), Unit cost, Transport, Landing (RM), Party
  price (RM), Selling (RM), Party margin, Note; Category / Brand / Cost method filters, "As of",
  Excel export (list-query export, as `ProductsList.tsx:1170`). "Add products" opens the shared
  picker (`products/[id]/components/ProductTargetPicker.tsx`, `useProductTargetPicker` with
  `sourceProductId` made optional); Remove = Unlink, a deferred action.
- **Products > Party costing** index: every customer with a costing profile (party, code, AutoCount
  debtor type, customer group, mark-up, method, products, active); a row opens that customer's
  Costing tab. Gated on `products.cost.view`.
- Product Pricing tab: "Party prices" card (party, mark-up, method used, party price, party margin).
- Gates: everything above needs `products.cost.view`; creating/editing a profile and its products
  needs a new `products.party_costing.manage` (management set + admin). A dealer never sees cost or
  these lists (management decision 9 Nov): staff-only routes, no portal/contact route, not exposed to
  the MCP server; tests assert a contact session and an API-key-only caller get 403/404.

What a profile does NOT carry yet, each with its trigger: a per-product mark-up within a party
(first party that asks for one), price tiers / quantity breaks (dealer tiers phase: a tier may
become a shared profile many dealers point at), a "whole category" selection rule (a party whose
range changes faster than staff can tick it).

## 4. Worked cases

Dev data is not reachable from the cloud sandbox; case 1 is the owner's workbook row, the rest are
illustrative inputs (crew can swap in dev rows on the test copy). Rate RMB: 0.625 MYR (1.6) from
1 Nov 2026, 0.617284 (1.62) from 1 Sep 2026; USD 4.40.

| # | Product | Rule | Supplier cost | Landing | Bath Plus party price (x1.08) |
|---|---|---|---|---|---|
| 1 | WB 245 basin (CGB9032B, workbook) | + RM 8 | RMB 34.50 | 21.5625; 23.71875; **31.71875** -> RM 31.72 | **RM 34.26** |
| 2 | Tap T-1xx | x 1.07 | RMB 120.00 | RM 88.28 (88.275) | RM 95.34 |
| 3 | Kitchen sink K-2xx | x 1.10 | RMB 260.00 | RM 196.63 (196.625) | RM 212.36 |
| 4 | Shower S-3xx, USD supplier | x 1.07 | USD 20.00 | RM 103.58 | RM 111.86 |
| 5 | Accessory A-4xx | x 1.07 | none | "No cost (method: Primary supplier)" | blank + flagged |

WB 245, selling RM 79.00, one product under each method (suppliers A primary RMB 34.50, B RMB
38.00, L MYR 42.00, D EUR 7.50 with no EUR rate on file):

| Method | Basis | Achieved mark-up | Bath Plus party price |
|---|---|---|---|
| Primary supplier (SUP-A01) | RM 31.72 | 149.06% | RM 34.26 |
| Selected supplier (SUP-B07) | RM 34.13 (34.125) | 131.50% | RM 36.86 (36.855) |
| Average of 3 supplier prices (SUP-D03 skipped: no rate for EUR) | RM 40.01 (40.014583) | 97.43% | RM 43.22 |
| Last PO price (RMB 34.50, 14 Oct 2026, at 1.62) | RM 31.43 (31.425926) | 151.38% | RM 33.94 |

## 5. Edge cases

- No cost under the chosen method: "No cost (method: X)"; mark-up blank; export cost blank + note.
- No rate in force on the date for a currency: "No rate for USD on <date>"; that supplier is skipped
  by Average and named.
- Rate changes on 1 Dec: costs as of 30 Nov use the old rate, as of 1 Dec the new; the Pricing tab
  names the rate and its effective date.
- MYR supplier: rate 1; SST still applied (owner Q1 answer: one SST setting, no exemption asked).
- Category without a transport rule and no product override: + 0, flagged "No transport rule".
- Several packaging rows in force on one link: the `standard` row; otherwise the cheapest, named.
- Product override "Selected supplier" whose link is later deleted: "Selected supplier no longer
  linked", no fallback.

## 6. Answers to card v4 (crew, 11 Nov)

- Q8 (a): the costing party is the `customers` (debtor) row, profile in separate tables.
- Q9 (a): Bath Plus ALREADY exists as a debtor on the dev copy (`sorento_prod_1104`, 4 Nov prod
  copy): `customer_code` 304-R017, name "RELATED - BATHPLUS SDN BHD", `debtor_type` project,
  `autocount_debtor_type` IC, `customer_type` company, active. Use that row. No seed in the
  migration; the hand-test setup step creates its profile at 8%.
- Q6 (a) and Q7 (a) stand; every call flagged for veto is accepted. Mock v4 stands unless the owner
  objects.
- Correction found while writing the UAC: #2319 grants `products.cost.view` to `admin, director,
  purchasing_manager, purchasing, purchasing_executive` (`sca_0001_products_cost_view.py`,
  `GRANT_ROLE_SLUGS`, read from dev data there). There is no `management` / `manager` role slug in
  that set, so "management" here = `director` (+ `admin`); `products.party_costing.manage` is
  granted to those two only (AC-AX-04).

## 7. Build shape (after approval)

- One additive migration: `exchange_rates` (+ seed from `scm.currency_rate`);
  `customer_costing_profiles` + `customer_costing_products`; company settings `costing_sst_factor`,
  `costing_default_method`; product category `transport_mode` / `transport_value`; product
  `transport_mode_override` / `transport_value_override`, `cost_method_override`,
  `cost_method_supplier_id`; permission `products.party_costing.manage`.
- BE: `costing_service` (pure, dated steps), rate service writes dated rows and `load_rates` reads
  the row in force today, product costing endpoint, party costing profile CRUD + product
  link/unlink, party costing list-query resources (index + per party) + export.
- FE: Purchasing tab (extend `ProductSuppliersTab.tsx`), Pricing tab (+ Party prices card), customer
  Costing tab, Products > Party costing index, dated Currency rates panel, Costing section on
  System Settings.

## 8. Dependency on SUPPLIER-COST-ACCESS (#2319)

Build uses #2319's `app/services/cost_access.py` (`COST_VIEW_PERM`, `require_cost_view`,
`COST_AUDIT_KEYS`, `cost_hidden`) and its permission row. #2319 is an open draft (11 Nov). Two
ways to build: (a) wait for #2319 to merge, then branch the build off main (one alembic chain,
no foreign commits in this PR); (b) merge #2319's head into this branch now and re-merge main once
#2319 lands (this PR then shows #2319's diff until it merges). Preferred (a); the build can start
on the parts that do not touch the gate (rates, landing cost, methods) under (a) as well, with the
gate wired in when #2319 is on main. Either way the migration's `down_revision` chains after
`sca_0001_products_cost_view`. `markup_pct`
joins `COST_AUDIT_KEYS` so History masks it (AC-PC-09).

## 9. Slices (one lane, one PR; commits per slice)

1. Exchange rates: `exchange_rates` table + seed, rate-in-force service, `load_rates` switch,
   dated Currency rates panel.
2. Costing core: settings (SST, default method), category transport rule + product override,
   product cost-method override, pure `costing_service`, product costing endpoint, Purchasing tab
   columns, Pricing tab (view + edit).
3. Party costing: profile + products tables, CRUD + link/unlink, per-party list-query resource +
   export, Products > Party costing index, customer Costing tab, Pricing tab Party prices card,
   `useProductTargetPicker` without a source product.
4. Hardening: access sweep (API key, contact session, customer payloads, MCP catalog), customer
   merge carry, migration grants, History masking.

One additive migration file for the lane (grown slice by slice before the first push of build),
revision id <= 32 chars, re-parented with `scripts/alembic-reparent.sh` before the PR is marked
ready. Checked on a scratch copy in this sandbox (upgrade, downgrade, upgrade); the shared dev DB
gets a `crew-migration:` block of `IF NOT EXISTS` DDL.

## 10. Red-first test list (tester writes these before any implementation)

Backend, pytest on Postgres only (`tests/_pg_fixture.py`), each seeding its own chain (CI's DB is
empty). Every row names the AC it pins.

| File | Tests (AC) |
|---|---|
| `tests/test_costing_exchange_rates.py` | unique (currency, effective_from) -> 409 (ER-01); rate <= 0 refused (ER-01); in force on 31 Oct / 1 Nov / 1 Dec boundaries (ER-02); no row before D -> no-rate result, never 1 (ER-03); MYR row refused (ER-03); entry 1.6 units-per-MYR -> 0.625 stored, both directions returned (ER-07); add / edit / delete each write an audit row (ER-06); delete goes through the deferred-action registry (ER-06); routes keep `scm.dashboard.view` / `scm.config.manage` (ER-07) |
| `tests/test_scm_load_rates_dated.py` | `load_rates` returns today's in-force row with `as_of` = effective_from; a future row is ignored until its day (freeze date) (ER-04); an existing planner caller (`reorder_engine` conversion) gets the same number it got from `scm.currency_rate` for the seeded rows (ER-04) |
| `tests/test_costing_landing.py` (pure, no DB) | the five AC-LC-01 figures to full precision; 2 dp half-up only in the display helper (31.71875 -> 31.72, 212.355 -> 212.36); ADD applied after SST (kill: ADD before SST gives 32.51875); no transport rule -> +0 and flag (ST-03); product override beats category rule (ST-02) |
| `tests/test_costing_methods.py` | primary: in-force row by date, `standard` packaging first, else cheapest named (LC-02); no primary -> "Set a primary supplier" (LC-03); selected supplier + its link deleted -> "no longer linked" (LC-03); average 40.014583 with EUR link skipped and named (LC-03; kill: counting the skipped link as 0 gives 30.01); last PO at the PO-date rate -> 31.425926 (LC-03; kill: today's rate gives 31.71875); precedence product > party > company, with source named (LC-04; kill: swapped order); no fallback (LC-05); selected supplier refused on a party profile and as company default (LC-06) |
| `tests/test_costing_settings.py` | SST and default method read with defaults 1.10 / primary, write audited (ST-01); category rule and product override CRUD, mode in (add, multiply), value > 0 (ST-02) |
| `tests/test_costing_page_routes.py` (v5) | page rows in Company standard and party views with the CG-03 / CG-04 figures; batch save writes only changed cells, one audit row each, refused without manage (CG-08); import dry run writes nothing, apply writes only mark-up / transport / method, cost column ignored (CG-10); row history (CG-11); `list_price` unchanged and no AutoCount client called (CG-14). Older rows below kept for the costing core: |
| `tests/test_product_costing_routes.py` | Purchasing rows: per-link landing, selling = list_price on every row, mark-up 149.06 / 131.50 / 45.76, EUR link "no rate" (PT-01); Pricing payload: breakdown steps, method + source, last PO check, achieved mark-up (PT-02); Party prices card lists each party holding the product with party price + margin (PT-03); `products.list_price` unchanged after every costing write and no AutoCount client is called (monkeypatched to fail) (PT-04); 403 without `products.cost.view` (PT-05) |
| `tests/test_party_costing_profiles.py` | one profile per customer, markup >= 0, method enum without selected (PC-01, LC-06); add 2 then same 2 -> 2 rows; 501 ids -> 422; one product on two parties (PC-02); Bath Plus-shaped fixture (code 304-R017, 8%) WB 245 -> 34.25625 / 130.61% (PC-03); manage permission required for create / edit / link / unlink, view permission alone -> 403 (PC-08); unlink goes through the deferred-action registry (PC-08); profile + link audit rows, `markup_pct` masked for a reader without cost view (PC-09) |
| `tests/test_party_costing_list_export.py` | per-party list-query resource: columns, filters (category, brand, method), search, as-of date changes the rate used (PC-05); export workbook read back with openpyxl: header names party + as-of, numeric cells are numbers, no-cost row blank + note (PC-06); index resource lists only customers with a profile, with debtor type + group (PC-07) |
| `tests/test_party_costing_access.py` | every costing route: no cost view -> 403, admin bypass -> 200 (AX-01); bare `X-API-Key` -> 401/403, contact portal session -> 401/403 (AX-02); customer detail / list / list-query export / portal order payloads carry no `markup`/`costing` key (AX-03); MCP catalog (`sorento_crm_mcp`) exposes no costing tool or path (AX-02) |
| `tests/test_party_costing_customer_merge.py` | merge with profile on retired only -> moves; on both -> survivor's kept, products unioned, logged (PC-10) |
| `tests/test_costing_migration.py` | upgrade on a scratch schema: tables, constraints, seed of one dated row per `scm.currency_rate` row, rerun adds nothing (ER-05); `products.party_costing.manage` granted to admin + director only (AX-04); downgrade drops only what it added |

Frontend, vitest (jsdom), next to the component (v5):

| File | Tests (AC) |
|---|---|
| `products/costing/components/CostingView.test.tsx` | hidden without cost view, menu item absent (CG-01); Sheet1 column order, explicit sizes, fixed resizable layout, `listingKey` (CG-01); party picker empty = Company standard, value in URL (CG-02); Company standard shows achieved mark-up and Final = Selling, no Margin (CG-03); party view Final / Margin and header chips (CG-04); reason pills, never "0.00" for unknown, row marker (CG-05); row expand supplier columns (CG-06); filters + As of in URL (CG-07); export config kind listQuery (CG-09) |
| `products/costing/components/CostingView.edit.test.tsx` | Edit swaps the three cells to inputs in the same columns, others stay text; mark-up input absent in Company standard (CG-08); clearing restores the inherited value; "applies to every party" on transport / method; Final recomputes while typing; Save sends one batch with only changed cells; Edit hidden without manage (CG-08) |
| `products/costing/components/CostingImportDialog.test.tsx` | Import disabled until a Test of the same file; report counts and reasons; Cost column reported as ignored (CG-10) |
| `products/costing/components/CostingSettingsDialog.test.tsx` | three line tabs; dated rates with status and both directions, entry in units per MYR converts, delete deferred (ER-06, ER-07, CG-13) |
| `products/[id]/components/ProductTargetPicker.noSource.test.tsx` | the hook works with no source product and marks already-added ids (CG-12) |

Browser pass (agent-browser, cloud): sidebar from `/` to Products > Costing; Company standard
view; pick 304-R017; set up 8%, add WB 245 via the picker; Edit a mark-up and a transport, Save,
open the row History; export, edit the file, Test, Import; Settings: add a 1 Dec RMB rate; a user
without cost view sees no menu item and gets 403; 375 px and 1280 px.

Kill tests (reviewer): ADD before SST; average counting a skipped link as 0; last PO at today's
rate; rate lookup with `<` instead of `<=`; precedence party > product; removing
`require_cost_view` from any one costing route; `markup_pct` dropped from `COST_AUDIT_KEYS`. Each
must turn at least one test red.

## Status log


- 10 Nov: lane opened, data mapped (section 1), behaviour card posted on PR #2321.
- 10 Nov: mock written (4 frames + element map), checked at 375 and 1280 px, no horizontal scroll.
- 10 Nov 23:3x: owner answered Q1-Q4; card v2 (sections 2-7) + mock v2. Q5 renamed Bath Plus, being re-asked by crew.
- 10 Nov 23:4x: Q5 answered as a generic business partner model; card v3 (3.3, 6, 7) + mock v3, Q6-Q7 asked.
- 10 Nov 23:5x: costing moves onto the party (customers row + profile table), card v4 (3.3, 6, 7) + mock v4, Q8-Q9 asked.
- 11 Nov: Q8 (a), Q9 (a) answered (Bath Plus = 304-R017); plan final, UAC file, red-first test list (section 10). Waiting on owner approval of mock v4.
- 11 Nov 00:2x: owner reshaped the lane to one costing page (Sales > Targets pattern); plan v5 (section 0), UAC section CG, mock v5, questions QA-QE.
