# UAC: Product costing (lane PRODUCT-COSTING)

Plan: `PLAN-product-costing-10nov.md`. Mock v5 (as amended 11 Nov 00:3x): `mockups/product-costing-10nov-mockup.html`.
Owner 00:3x: QA (a) row mark-up per party; QC no Excel import (Export stays); QD (a) page Edit then
one Save, as Sales > Targets. Working answers until the owner confirms: QB (a), QE (a) with "Has
cost" on by default.
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

## Costing page (CG) - v5, the workbook in the system (owner 11 Nov 00:2x)

- AC-CG-01 Products > Costing is one DataGrid page, visible only with `products.cost.view`
  (menu item absent, route 403 otherwise). Columns in Sheet1 order: Category, Code, Name,
  Supplier, Cost (currency + amount), Rate (units per MYR 1, as the workbook writes it), SST,
  Transport (mode + value), Landing (RM), Cost method, Mark-up, Final (RM), Selling (RM), Margin.
  Fixed layout, resizable, explicit sizes, saved column choices (`listingKey`).
- AC-CG-02 A party picker sits above the grid: empty = "Company standard" (default); a customer
  (e.g. 304-R017 RELATED - BATHPLUS SDN BHD) = that party's view. The picked party and filters
  live in the URL.
- AC-CG-03 Company standard view (QB a, working answer): every active product (QE); Mark-up =
  achieved = (selling - landing) / landing; Final = Selling = AutoCount `list_price`; read-only
  except Transport and Cost method in Edit; no Margin column. WB 245: 149.06%.
- AC-CG-04 Party view: the party's products only; Mark-up = the row's mark-up, else the party's;
  Final = landing x (1 + mark-up); Margin = (selling - final) / final. WB 245 at 8%: 34.25625 ->
  34.26, 130.61%. Jacuzzi row at 10%: 1692.375 -> 1861.6125, 114.81%. Header chips: party
  mark-up, party cost method, "as of" date, product count.
- AC-CG-05 Unknown values are blank with a reason pill ("No cost", "No rate for EUR on <date>",
  "Set a primary supplier", "No transport rule"), never 0. A value set on the row (not inherited)
  carries a marker.
- AC-CG-06 A row opens to its suppliers: supplier, primary, lead time, cost, landing, final at
  this view's mark-up, margin if bought there (WB 245, Bath Plus: A 130.61%, B 114.35%, L 34.96%).
- AC-CG-07 Filters: Category, Brand, Cost method, Has cost; search by code / name; "As of" date
  (default today) changes which supplier cost and rate are used. "Has cost" is ON when the page
  opens (QE working answer), so the page opens on the costed products; turning it off shows the
  gaps; the filter state lives in the URL like the others.
- AC-CG-08 Edit / Save in place, exactly as Sales > Targets (QD a): press Edit on the page, the
  same grid and columns turn editable, one Save writes everything (Cancel discards). Editable: Mark-up (party view only, per row, like
  the Excel (QA a); clearing returns to the party's), Transport (the product's override; clearing returns to
  the category rule) and Cost method (the product's override; clearing returns to party / company
  default). Transport and method edits say "applies to every party". Landing, Final and Margin
  recompute while typing. Save sends one batch; every changed cell writes one audit row. Cost,
  rate and SST are not editable here. Editing needs `products.party_costing.manage`.
- AC-CG-09 Export: the whole filtered set to Excel through the list-query export, Sheet1 column
  order, numbers as numbers, a header row naming the view (Company standard or the party) and the
  "as of" date.
- AC-CG-10 No Excel import (owner, QC): no Import action, dialog, route or service. Data is
  maintained on the page.
- AC-CG-11 Row History: who changed that row's mark-up, transport or method, when, old -> new.
- AC-CG-12 Add products / Remove (party view): the shared product picker, up to 500 per add;
  Remove is an Unlink deferred action. A party's default mark-up and method are edited from the
  header chips (manage permission).
- AC-CG-13 Settings dialog from the page header: three line tabs, Exchange rates (dated, AC-ER),
  SST and default method (AC-ST-01), Transport by category (AC-ST-02).
- AC-CG-14 The selling price is never written: no costing route or job sends a price to
  AutoCount or changes `products.list_price`.

## Party data (PC)

- AC-PC-01 A costing profile belongs to one `customers` row: default mark-up % (required,
  >= 0), optional cost method override (Primary / Average / Last PO), active. At most one per customer.
- AC-PC-02 A profile's products are a static set with an optional per-row mark-up override;
  adding a product twice is a no-op; one product can be on many parties.
- AC-PC-09 Profile, row mark-up and link / unlink changes are audited; mark-up values are masked
  in History for a reader without `products.cost.view`.
- AC-PC-10 A customer merge carries the profile and its products onto the survivor (survivor's
  profile wins if both have one; product sets are unioned, survivor's row mark-up wins).

## Access (AX)

- AC-AX-01 Every costing read (product costing, party list, index, export) needs
  `products.cost.view`: 403 without it. Admin / superadmin pass by the existing bypass.
- AC-AX-02 A bare `X-API-Key` caller and a contact (portal) session get 401/403 on every costing
  route; no portal route and no MCP tool serves costing.
- AC-AX-03 Customer list, customer detail, customer export, product payloads, the portal and MCP
  carry no costing field.
- AC-AX-04 The migration grants `products.party_costing.manage` by role slug to `admin` and
  `director` only (the management roles in #2319's `sca_0001_products_cost_view` grant set,
  read from dev data there); not to `purchasing_manager`, `purchasing`, `purchasing_executive`,
  sales or dealer roles. superadmin passes by bypass. Nothing is revoked.
