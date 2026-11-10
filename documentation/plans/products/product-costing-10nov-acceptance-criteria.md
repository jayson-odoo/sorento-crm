# UAC: Product costing (lane PRODUCT-COSTING)

Plan: `PLAN-product-costing-10nov.md`. Mock v4: `mockups/product-costing-10nov-mockup.html`.
Answers: owner 10 Nov 23:3x / 23:4x / 23:5x; crew 23:5x+ (Q6 a, Q7 a, Q8 a, Q9 a, vetoable calls accepted).
Cost permission `products.cost.view` comes from SUPPLIER-COST-ACCESS (PR #2319,
`app/services/cost_access.py`: `COST_VIEW_PERM`, `require_cost_view`, `COST_AUDIT_KEYS`).

Figures: full precision inside, 2 dp half-up only at display and export. "No value" is blank +
a reason, never 0.

## Exchange rates (ER)

- AC-ER-01 A rate row is (currency, effective from, MYR per 1 unit > 0, note). One row per
  currency per date; a second row for the same pair is refused (409).
- AC-ER-02 The rate for currency C on date D is the row with the latest effective-from <= D.
  RMB 0.617284 from 1 Sep and 0.625 from 1 Nov: 31 Oct -> 0.617284, 1 Nov -> 0.625, 1 Dec with a
  row 0.613497 from 1 Dec -> 0.613497.
- AC-ER-03 No row on or before D -> "no rate" (the caller shows "No rate for C on D"); never 1.
  MYR is 1 by definition and has no row; adding an MYR row is refused.
- AC-ER-04 The SCM planner's `load_rates` returns the row in force TODAY from the dated table,
  with `as_of` = that row's effective-from; a future-dated row does not apply before its day.
- AC-ER-05 The migration seeds one dated row per existing `scm.currency_rate` row
  (effective-from = its `as_of`, else the migration date); rerunning it adds nothing.
- AC-ER-06 Every add / edit / delete of a rate row writes an audit row (who, when, old, new).
  Delete is a server-deferred action (no confirm dialog).
- AC-ER-07 Entry accepts "MYR per 1 unit" or "units per MYR 1" (1.6 -> 0.625); the list shows
  both directions. Reading rates keeps `scm.dashboard.view`, editing keeps `scm.config.manage`
  (`app/api/v1/scm/config.py:42-43`, unchanged).

## Costing settings and transport (ST)

- AC-ST-01 Company settings: SST factor (default 1.10) and default cost method (default
  Primary supplier). Both returned by the settings read and audited on change.
- AC-ST-02 A product category has an optional transport rule: mode ADD (flat MYR per unit) or
  MULTIPLY (factor), and a value. A product has an optional override of the same shape; the
  product's override wins over its category rule.
- AC-ST-03 No rule and no override -> transport adds 0 and the result carries the flag
  "No transport rule".

## Landing cost and cost method (LC)

- AC-LC-01 Landing cost = unit cost x rate(D) x SST, then ADD value or x MULTIPLY value.
  Workbook row: RMB 34.50, rate 0.625, SST 1.1, ADD 8 -> 31.71875 (shows 31.72).
  RMB 120, MULTIPLY 1.07 -> 88.275. RMB 260, MULTIPLY 1.1 -> 196.625. USD 20 at 4.40, x1.07 ->
  103.576. MYR 42, ADD 8 -> 54.20 (rate 1, SST still applied).
- AC-LC-02 Supplier cost used for a link = the cost row in force on D (`price_in_force`), the
  `standard` packaging row first, else the cheapest packaging row (named).
- AC-LC-03 Methods:
  - Primary supplier: the primary link's cost. No primary -> "Set a primary supplier".
  - Selected supplier: the product override's supplier. Link removed -> "Selected supplier no
    longer linked".
  - Average: simple mean of the landing costs of every link with a cost AND a rate on D; links
    skipped for no cost / no rate are listed. WB 245 (A 31.71875, B 34.125, L 54.20, D EUR no
    rate) -> 40.014583, D named as skipped.
  - Last PO price: the latest PO line unit cost for the product, converted at the rate in force
    on the PO's issue date. RMB 34.50 on 14 Oct at 0.617284 -> 31.425926.
- AC-LC-04 Method precedence: product override > party override > company default. The result
  always names the method and its source (product / party / company).
- AC-LC-05 No silent fallback: a method that yields nothing returns "No cost (method: X)".
- AC-LC-06 "Selected supplier" is offered only as a product override, never on a party profile
  or as the company default.

## Product tabs (PT)

- AC-PT-01 The product Suppliers tab is renamed Purchasing (`?tab=suppliers` still opens it).
  Per link: supplier code, primary, lead time, currency, unit cost, landing cost (RM), selling
  (RM, the product's AutoCount list price on every row), mark-up if bought here =
  (selling - landing) / landing. WB 245 at RM 79: A 149.06%, B 131.50%, L 45.76%, D "No rate for
  EUR on <date>" and no mark-up.
- AC-PT-02 A new Pricing tab, only with `products.cost.view`: cost basis breakdown (method
  chip + source, supplier cost, rate with its effective date, SST, transport with its source,
  landing cost), last PO price as a check, selling price read-only, achieved mark-up =
  (selling - basis) / basis. Edit swaps in place: cost method (clearable to company default;
  each option previews its basis and mark-up), selected supplier, transport override.
- AC-PT-03 Pricing tab "Party prices" card: every party whose costing list holds the product:
  party, mark-up, method used, party price, party margin. Read-only.
- AC-PT-04 The selling price is never written: no costing route or job sends a price to
  AutoCount or changes `products.list_price`.
- AC-PT-05 Without `products.cost.view` the Pricing tab is absent and its routes answer 403;
  a `?tab=pricing` link falls back to Overview.

## Party costing (PC)

- AC-PC-01 A costing profile belongs to one `customers` row: mark-up % (required, >= 0),
  optional cost method override (Primary / Average / Last PO), active. At most one per customer.
- AC-PC-02 A profile's products are a static set; adding a product twice is a no-op; one
  product can be on many parties. Add takes up to 500 product ids per call.
- AC-PC-03 Party price = landing x (1 + mark-up). Party margin = (selling - party price) /
  party price. Bath Plus (304-R017, 8%), WB 245: 34.25625 -> 34.26; margin 130.61% at RM 79.
- AC-PC-04 The customer page has a Costing tab only with `products.cost.view` (view and edit
  pages alike). No profile: empty state (heading + hint, no body button) and the header CTA
  "Set up costing" (only with `products.party_costing.manage`).
- AC-PC-05 The party costing list: Code, Name, Category, Cost method (+ source), Unit cost,
  Transport, Landing (RM), Party price (RM), Selling (RM), Party margin, Note; search, Category /
  Brand / Cost method filters, "As of" date (default today), fixed-layout resizable DataGrid.
- AC-PC-06 Excel export of that list: the columns in the plan section 3.3, numbers as numbers,
  header row naming the party and the "as of" date; unknown cost exported blank with its note.
- AC-PC-07 Products > Party costing index: every customer with a profile (code, party,
  AutoCount debtor type, customer group, mark-up, method, products, status); a row opens the
  customer's Costing tab.
- AC-PC-08 Create / edit a profile and add / remove its products needs
  `products.party_costing.manage` (+ `products.cost.view`); remove is an Unlink deferred action.
- AC-PC-09 Profile changes and product link / unlink are audited; `markup_pct` is masked in
  History for a reader without `products.cost.view`.
- AC-PC-10 A customer merge carries the profile and its products onto the survivor (survivor's
  profile wins if both have one; product sets are unioned).

## Access (AX)

- AC-AX-01 Every costing read (product costing, party list, index, export) needs
  `products.cost.view`: 403 without it. Admin / superadmin pass by the existing bypass.
- AC-AX-02 A bare `X-API-Key` caller and a contact (portal) session get 401/403 on every costing
  route; no portal route and no MCP tool serves costing.
- AC-AX-03 Customer list, customer detail, customer export, the portal and MCP payloads carry
  no costing field.
- AC-AX-04 The migration grants `products.party_costing.manage` by role slug to `admin` and
  `director` only (the management roles in #2319's `sca_0001_products_cost_view` grant set,
  read from dev data there); not to `purchasing_manager`, `purchasing`, `purchasing_executive`,
  sales or dealer roles. superadmin passes by bypass. Nothing is revoked.
