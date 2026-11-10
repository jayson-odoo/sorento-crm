# PLAN: Product costing - Purchasing vs Pricing tabs + B Plus costing view

Status: Plan, waiting on owner (behaviour card + mock `mockups/product-costing-10nov-mockup.html` on PR #2321). Build only after approval.
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

## 2. Rules (from the meeting + workbook)

- Landing cost (MYR) = supplier unit cost / rate x SST, then transport.
  - rate: RMB 1.6 per MYR (other currencies: their own rate); SST 1.1 (10%, goods).
  - transport ADD (ceramics, WCs, jacuzzi): + flat MYR per unit (e.g. 8).
  - transport MULTIPLY (accessories, sinks, taps, hose, valves, shower): x 1.07; kitchen sinks x 1.1.
- B Plus cost price = landing cost x (1 + B Plus mark-up 8%).
- Selling price is standard per product; it does not move with the chosen supplier.
- Purchasing tab, per supplier: mark-up if bought from this supplier = (selling price - that
  supplier's landing cost) / that landing cost. Converted to MYR first (the workbook sheet 2 mixes
  currencies; treated as a layout sketch only).
- Cost (any of the above) visible only with `products.cost.view`; dealers never.
- Rounding: compute in full precision, show 2 dp (half up) only at display/export.

## 3. Worked cases

Dev data is not reachable from the cloud sandbox; case 1 is the owner's workbook row, cases 2-5
use illustrative inputs (crew can swap in dev rows on the test copy).

| # | Product (masked) | Category rule | Supplier cost | Landing cost | B Plus (x1.08) |
|---|---|---|---|---|---|
| 1 | WB 245 basin (CGB9032B, workbook) | ceramic, + RM 8 | RMB 34.50 | 34.5/1.6 = 21.5625; x1.1 = 23.71875; +8 = **31.71875** -> RM 31.72 | **RM 34.26** (34.25625) |
| 2 | Tap T-1xx | tap, x 1.07 | RMB 120.00 | 75; 82.5; **88.275** -> RM 88.28 | RM 95.34 (95.337) |
| 3 | Kitchen sink K-2xx | kitchen sink, x 1.10 | RMB 260.00 | 162.5; 178.75; **196.625** -> RM 196.63 | RM 212.36 (212.355) |
| 4 | Shower set S-3xx, USD supplier | shower, x 1.07 | USD 20.00 at 4.40 MYR | 88; 96.8; **103.576** -> RM 103.58 | RM 111.86 |
| 5 | Accessory A-4xx, no supplier cost | accessory, x 1.07 | none | "No cost" | "No cost", row flagged in export |

Purchasing tab for case 1 with two suppliers and a standard selling price of RM 79.00:
supplier A (primary) RMB 34.50 -> landing RM 31.72 -> mark-up 149.06%; supplier B RMB 38.00 ->
landing RM 34.13 (34.125) -> mark-up 131.50%. Selling price stays RM 79.00 on both rows.

## 4. Edge cases (proposed behaviour)

- No supplier cost: landing cost "No cost"; Pricing tab mark-up blank; B Plus row exported with
  blank cost and a "No cost" note, never a 0.
- Several suppliers: Pricing tab cost basis = primary supplier's cost in force today; every
  supplier still gets its own row and mark-up on the Purchasing tab.
- No primary set but suppliers exist: no cost basis, "Set a primary supplier" state (no silent pick).
- Non-RMB currency: converted with that currency's rate; no rate stored -> "No rate for USD", no number.
- MYR supplier: rate 1; SST still applied (owner to confirm if local purchases carry SST: Q1).
- Category with no transport rule: transport = none (add 0), row flagged "No transport rule".
- Several packaging rows in force on the primary link: the `standard` packaging row; else the cheapest (Q4).

## 5. Questions (5), each with a recommendation

- Q1 Where rate / SST / transport live. (a) rate reuses `scm.currency_rate` (one rate source for
  SCM and costing), SST one company setting, transport mode + value per product category with an
  optional per-product override; changes audited (who/when/old/new) instead of history tables;
  (b) a separate costing rate per currency + everything per product. Rec (a): one rate source,
  and the workbook's rules are already per category.
- Q2 Mark-up. (a) the Pricing tab mark-up is the ACHIEVED mark-up = (selling price - cost basis)
  / cost basis, read-only; (b) a stored target mark-up % per product (category default) that
  computes a suggested selling price. Rec (a) now: the selling price is AutoCount's `list_price`
  (synced, Q3), so a stored mark-up would be a second number that disagrees with it.
- Q3 Selling price source. (a) keep AutoCount `list_price` as the standard selling price
  (read-only in CRM, as today); (b) CRM owns a selling price computed from cost x mark-up and
  pushes it to AutoCount. Rec (a): the sync already overwrites `list_price`, (b) needs a write-back.
- Q4 Which cost a product uses. (a) primary supplier's cost row in force today (dated cost lists),
  last PO price shown beside it as a check; (b) latest PO price. Rec (a): it is the price the
  supplier quotes now, and it exists per supplier; the PO price lags and only exists after an order.
- Q5 What "B Plus" is in the system. (a) not a company: a costing list "B Plus" = a selected-product
  flag + one mark-up setting (8%), screen + Excel export under Products; generalise to a list table
  when a second list (dealer tiers) arrives; (b) a separate company / price-list module now.
  Rec (a): one list today, simplest thing that works; dealer tiers are a named later trigger.

## Status log

- 10 Nov: lane opened, data mapped (section 1), behaviour card posted on PR #2321.
- 10 Nov: mock written (4 frames + element map), checked at 375 and 1280 px, no horizontal scroll.
