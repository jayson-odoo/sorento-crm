# PLAN: Product costing - Purchasing vs Pricing tabs + Bath Plus costing view

Status: Plan, owner answered Q1-Q4 (10 Nov 23:3x), Q5 being re-asked; card + mock v2 (`mockups/product-costing-10nov-mockup.html`) on PR #2321. Build only after approval.
Track: full (migration + cost permission gating).

Lane: PRODUCT-COSTING. Source: owner + management meeting 9 Nov 2026 "Project Internal Costing",
owner's workbook Internal_Costing_Formula.xls (numbers are the owner's draft). Depends on
SUPPLIER-COST-ACCESS (PR #2319, open draft) for the `products.cost.view` permission.

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
- Q5: "B Plus" was a mishearing: it is **Bath Plus** (workbook "Bath+ cost price"; AutoCount
  company DB `AED_BATHPLUS`), the sister company that sells Sorento products. Crew re-asks Q5;
  working assumption stays (a): a per-product "In Bath Plus costing list" flag + one Bath Plus
  mark-up setting (8%), list + Excel export, no company/price-list module.

## 3. Rules

- Landing cost (MYR) = supplier unit cost x rate (MYR per unit, in force on the date) x SST, then
  transport (category rule, or the product's override):
  - ADD (ceramics, WCs, jacuzzi): + flat MYR per unit (e.g. 8).
  - MULTIPLY (accessories, sinks, taps, hose, valves, shower): x 1.07; kitchen sinks x 1.1.
- Bath Plus cost price = landing cost x (1 + Bath Plus mark-up 8%).
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
  not company-scoped, like `scm.currency_rate` today (Bath Plus buys in the same currencies).
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
  Bath Plus list has an "As of" date). A last-PO cost is converted at the rate in force on the PO's
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
- The method is shown next to every cost: Pricing tab ("Primary supplier, SUP-A01"), Bath Plus
  grid column "Cost method", export column "Cost method".

## 4. Worked cases

Dev data is not reachable from the cloud sandbox; case 1 is the owner's workbook row, the rest are
illustrative inputs (crew can swap in dev rows on the test copy). Rate RMB: 0.625 MYR (1.6) from
1 Nov 2026, 0.617284 (1.62) from 1 Sep 2026; USD 4.40.

| # | Product | Rule | Supplier cost | Landing | Bath Plus (x1.08) |
|---|---|---|---|---|---|
| 1 | WB 245 basin (CGB9032B, workbook) | + RM 8 | RMB 34.50 | 21.5625; 23.71875; **31.71875** -> RM 31.72 | **RM 34.26** |
| 2 | Tap T-1xx | x 1.07 | RMB 120.00 | RM 88.28 (88.275) | RM 95.34 |
| 3 | Kitchen sink K-2xx | x 1.10 | RMB 260.00 | RM 196.63 (196.625) | RM 212.36 |
| 4 | Shower S-3xx, USD supplier | x 1.07 | USD 20.00 | RM 103.58 | RM 111.86 |
| 5 | Accessory A-4xx | x 1.07 | none | "No cost (method: Primary supplier)" | blank + flagged |

WB 245, selling RM 79.00, one product under each method (suppliers A primary RMB 34.50, B RMB
38.00, L MYR 42.00, D EUR 7.50 with no EUR rate on file):

| Method | Basis | Achieved mark-up | Bath Plus |
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

## 6. Open (crew re-asks Q5 as Bath Plus)

Working assumption (a). Nothing else open; two calls made on the owner's answers and flagged for
veto: exchange rates are group-wide (not per company), and the "average" is the mean of current
supplier prices, not a PO-weighted average.

## 7. Build shape (after approval)

- One additive migration: `exchange_rates` (+ seed from `scm.currency_rate`); company settings
  `costing_sst_factor`, `costing_default_method`, `bath_plus_markup_pct`; product category
  `transport_mode`/`transport_value`; product `transport_mode_override`/`transport_value_override`,
  `cost_method_override`, `cost_method_supplier_id`, `in_bath_plus_costing`.
- BE: `costing_service` (one pure function per step, dated), rate service writes dated rows, `load_rates`
  reads the row in force today, product costing endpoint, Bath Plus list-query resource + export.
- FE: Purchasing tab (extend `ProductSuppliersTab.tsx`), Pricing tab, Bath Plus list page, dated
  Currency rates panel, Costing section on System Settings.

## Status log


- 10 Nov: lane opened, data mapped (section 1), behaviour card posted on PR #2321.
- 10 Nov: mock written (4 frames + element map), checked at 375 and 1280 px, no horizontal scroll.
- 10 Nov 23:3x: owner answered Q1-Q4; card v2 (sections 2-7) + mock v2. Q5 renamed Bath Plus, being re-asked by crew.
