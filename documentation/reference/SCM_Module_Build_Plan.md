# Supply Chain & Inventory Optimisation - Module Build Plan (PoC-as-Module)

**See also:** `documentation/reference/SCM-UPLOAD-FORMATS.md` for what the supplier stock
list, proforma invoice and packing list uploads accept, column by column.

**For:** Claude Code build + `/grill` adversarial review
**Status:** Draft for interrogation. Every section marked `GRILL` is a decision I want pressure-tested, not a settled answer.
**Author context:** Sorento Phase 2, Requirement #27. This is a decision-support co-pilot that replaces AutoCount's naive min/max reorder logic with cash-aware, judgment-augmented planning. It is NOT autopilot.

---

## 0. The one principle that makes this a module and not a throwaway PoC

**The SCM core never reads AutoCount. It reads our own canonical tables.**

AutoCount is deferred, but the schema those tables expose is designed *now* as the contract AutoCount will later sync into. For the PoC we populate the tables from what we already have (product, stock, stock ledger, supplier, warehouse) plus a seed script for the new ones (sales order, PO, supplier-product). When AutoCount integration lands, it becomes an ETL job that writes into the same tables - the core, the ruleset engine, and the dashboard do not change.

Consequences that must hold from commit 1:

- Every table the core consumes has a `source_system` column (`manual` | `seed` | `autocount`) and a `source_ref` (external key placeholder). Nullable now, populated later.
- The core queries a **read model / view layer**, never raw tables directly, so the physical source can change beneath it.
- No AutoCount-specific field names leak into the core. If AutoCount calls it `DocKey`, that stays in the sync layer and maps to our `source_ref`.

If any part of the build couples the reorder logic to an AutoCount shape, that's a defect regardless of whether it "works" in the demo.

---

## 1. Scope

**In scope (this build):**
1. Canonical data model - extend existing base (product, stock, stock ledger, supplier, warehouse) with the missing entities (sales order, purchase order, supplier-product link, and the SCM-specific tables).
2. **The reorder core** - deterministic engine: *when* to reorder and *how much*, driven by a configurable ruleset table.
3. Demand model - consumption rate from the stock ledger, with censored-demand handling.
4. Cash-constrained recommendation layer.
5. Visibility dashboard + recommendation review UI (accept / override, override captured).

**Explicit non-goals (deferred, do not build, but do not architecturally preclude):**
- AutoCount integration (swap-in later behind the table contract).
- Project registration and dealer order modules (SO table stands in for committed demand for now).
- Auto-execution of POs. **The platform never raises a PO.** It drafts a recommendation; a human raises the PO (in AutoCount, later). This is a hard rule, not a phase.
- LLM-computed quantities (see §7).
- Multi-echelon / inter-warehouse transfer optimisation.

---

## 2. Three-layer control (the architectural guardrail)

| Layer | Responsibility | Implementation | Never does |
|---|---|---|---|
| **Quantitative core** | forecast, safety stock, reorder point, net position, order qty, ABC/XYZ, cash-tied-up | deterministic code, reads ruleset table | call an LLM; hold business config in code |
| **Judgment layer** | human accept/adjust; override reason capture | UI + `recommendation_override` table | silently discard an override |
| **Semantic layer (LLM)** | explain a recommendation in words; draft PO text; answer "why this qty?" | GPT-4.1 mini / Gemini 2.5 Flash | compute or alter a quantity, ROP, or SS |

The boundary between core and semantic layer is the thing most likely to rot. The LLM receives computed numbers as input and produces prose as output. It has no path to change a number.

---

## 3. Data model

### 3.1 Existing base (assumed present - CONFIRM shape)

`GRILL 3.1` - I'm assuming these exist and are usable. Confirm each:

| Table | What the core needs from it | Open question |
|---|---|---|
| `product` | SKU id, description, product class/category, **colour variant granularity**, unit cost, active flag | **Is a colour a distinct SKU row, or an attribute of a parent SKU?** This decides forecast granularity. Sanitaryware dead stock accumulates at colour level, so the core must forecast at whatever level a colour is orderable. |
| `stock` | current on-hand per SKU per warehouse | Is it a live snapshot, or derived from the ledger? If snapshot, is it reconcilable against the ledger? |
| `stock_ledger` | timestamped in/out movements per SKU per warehouse | **Is it append-only and complete enough to reconstruct on-hand at any past date?** This is the backbone of demand history AND stockout-window detection. If it only goes back N months, forecasting depth is capped at N. |
| `supplier` | supplier id, name, currency | - |
| `warehouse` | warehouse id, location | Do we reorder per warehouse, network-wide, or per warehouse with a central buy? (see `GRILL 5.5`) |

### 3.2 New tables

**`supplier_product`** - the SKU↔supplier link. Without this, no reorder maths is possible.

```
supplier_product (
  id, supplier_id, product_id,
  lead_time_days,            -- declared for PoC; measured from PO↔GRN later
  lead_time_variability_days,-- std dev; NULL now, estimated
  moq,                       -- minimum order qty
  order_multiple,            -- carton / pack multiple
  unit_cost, currency,
  is_primary_supplier,       -- one SKU can have several suppliers
  source_system, source_ref
)
```

**`sales_order` + `sales_order_line`** - stands in for committed demand until project/dealer modules exist.

```
sales_order (id, so_number, customer_ref, order_date, status, source_system, source_ref)
sales_order_line (id, sales_order_id, product_id, warehouse_id,
                  qty_ordered, qty_delivered, line_status)
```
`GRILL 3.2a` - **committed stock = sum of (qty_ordered − qty_delivered) on open lines.** Does the existing/seed SO data distinguish delivered vs pending at line level? If not, "committed" is unreliable and net position is wrong.

**`purchase_order` + `purchase_order_line`** - models on-order / in-transit stock, and is the sink the recommendation drafts into.

```
purchase_order (id, po_number, supplier_id, issue_date, expected_date,
                status, source_system, source_ref)
purchase_order_line (id, purchase_order_id, product_id, warehouse_id,
                     qty_ordered, qty_received, unit_cost, currency, expected_date)
```
On-order = sum of (qty_ordered − qty_received) on open PO lines. For the PoC these are seeded; later, AutoCount POs sync here. The recommendation output can generate a **draft** PO (status = `draft_recommendation`) that a human confirms - but the platform never transmits it.

**`quotation` + `quotation_line`** (OPTIONAL this build - scaffold, don't wire into the trigger yet)
Soft forward-demand signal (quoted-but-not-ordered). Build the tables so the demand model *can* consume them later, but keep them out of the reorder trigger until validated. `GRILL 3.2b` - include or defer?

**`demand_event`** - the censored-demand capture. This is Sorento's structural edge; see §4.

```
demand_event (
  id, product_id, warehouse_id, event_ts,
  qty_requested,
  fulfillable boolean,       -- was stock available at time of ask?
  qty_short,                 -- requested − available
  channel,                   -- 'stock_enquiry' | 'so_line' | 'quotation'
  source_ref
)
```

**`reorder_policy`** - the ruleset. **This is the "core to define the ruleset" you asked for.** See §5.

```
reorder_policy (
  id, scope_type,            -- 'sku' | 'product_class' | 'abc_xyz_cell' | 'global'
  scope_ref,                 -- the id/class/cell this applies to
  policy_type,               -- 'reorder_point' | 'periodic_review' | 'min_max'
  service_level,             -- e.g. 0.95 → Z-score
  safety_stock_method,       -- 'statistical' | 'fixed_days' | 'manual'
  safety_days,               -- used if fixed_days
  review_period_days,        -- used if periodic_review
  min_override, max_override,-- manual guardrails
  forecast_window_days,      -- trailing window for demand rate
  is_active, priority        -- most specific active policy wins
)
```
Resolution order: SKU-specific → ABC/XYZ cell → product class → global. Most specific active policy wins. This keeps the founder's judgment configurable without code changes and without example-overfitting.

**`item_classification`** - computed ABC (value) × XYZ (demand variability), stored per SKU per run.

```
item_classification (product_id, warehouse_id, abc_class, xyz_class,
                     annual_value, demand_cv, computed_at)
```

**`purchasing_budget`** - the cash ceiling. Cash is the headline constraint and it lives outside AutoCount.

```
purchasing_budget (id, period_start, period_end, budget_amount, currency, set_by, note)
```
`GRILL 3.2c` - per month? per supplier? global? Who sets it and how often?

**`reorder_recommendation`** - engine output.

```
reorder_recommendation (
  id, run_id, product_id, warehouse_id, supplier_id,
  net_position, reorder_point, forecast_daily_demand, days_of_cover,
  recommended_qty, rounded_qty,        -- after MOQ/multiple
  unit_cost, cash_impact, currency,
  urgency_score, confidence_band,      -- from XYZ + data sufficiency
  triggered_reason,                    -- machine-readable
  explanation,                         -- LLM prose, generated from the numbers above
  status,                              -- 'proposed' | 'accepted' | 'overridden' | 'dismissed'
  created_at
)
```

**`recommendation_override`** - the training signal. Every override is the founder's private lost-demand / judgment estimate made explicit.

```
recommendation_override (
  id, recommendation_id,
  original_qty, override_qty,
  reason_code,               -- 'incoming_project' | 'colour_dying' | 'cash' | 'supplier_deal' | 'other'
  reason_text, overridden_by, overridden_at
)
```

---

## 4. Demand & unmet-demand model

**Base demand rate:** average daily demand over `forecast_window_days` from `stock_ledger` outbound movements. Start simple - moving average or weighted moving average. `GRILL 4.1` - do NOT build ARIMA/Prophet for the PoC; a transparent moving average the founder can understand beats a black box he won't trust. Agree?

**Censored-demand correction (the edge):** sales/outbound history understates demand during stockouts. Two mechanisms:

1. **Forward capture** - `demand_event` rows. When a stock enquiry (later: SO line, quotation) hits a SKU with zero available, log `fulfillable=false, qty_short`. Near-free because the enquiry channel already exists in the platform. **This must be switched on as early as possible - the signal only accrues forward; every day off is a day lost.**
2. **Historical reconstruction** - from the ledger, detect windows where on-hand = 0. Treat outbound = 0 during those windows as *censored*, not zero demand. Impute from the in-stock demand rate immediately before the window, or from colour variants that were in stock.

`GRILL 4.2` - for the PoC, is forward capture (mechanism 1) enough to demo the concept, with historical reconstruction (mechanism 2) as a fast-follow? Reconstruction depends on ledger depth (`GRILL 3.1`).

**Dead / slow stock:** SKUs with no outbound movement in `dead_stock_days` (configurable) surfaced as trapped cash. `GRILL 4.3` - is "no movement in N days" the right definition, or a turnover-ratio threshold? Founder's call.

---

## 5. The reorder core - trigger and quantity

This is the heart. All deterministic. All formulas below are the *default* method; the `reorder_policy` row selects which apply.

### 5.1 Net position (the number everything hangs off)

```
net_position = on_hand + on_order − committed
```
where on_order and committed come from open PO and SO lines (§3.2). **A recommendation computed without on_order is wrong** - open POs are stock-in-transit; ignoring them double-orders.

### 5.2 Forecast

```
avg_daily_demand = censored_adjusted_outbound(forecast_window_days) / forecast_window_days
```

### 5.3 Safety stock (method per policy)

- `statistical`: `SS = Z(service_level) × sqrt(lead_time_days) × σ_daily_demand`
  (extend to include lead-time variability once measured: `SS = Z × sqrt(LT×σ_d² + d²×σ_LT²)`)
- `fixed_days`: `SS = avg_daily_demand × safety_days`
- `manual`: from policy

`GRILL 5.3` - for the PoC, `fixed_days` is defensible and explainable; full statistical SS needs σ we may not have cleanly yet. Start `fixed_days`, expose `statistical` as the config option?

### 5.4 Trigger (when to reorder)

- `reorder_point`: trigger when `net_position ≤ ROP`, where `ROP = (avg_daily_demand × lead_time_days) + SS`
- `periodic_review`: on review cadence, trigger if `net_position < order_up_to_level`
- `min_max`: trigger when `net_position ≤ min`

### 5.5 Quantity (how much)

- Order-up-to: `qty = order_up_to_level − net_position`
  where `order_up_to_level = ROP + (avg_daily_demand × review_period_days)`
- Then **round to supplier constraints**: `rounded_qty = roundup(qty to order_multiple, min = moq)`

`GRILL 5.5` - **multi-warehouse.** Do we compute ROP/qty per warehouse, or network-wide then allocate? Sorento's real buying is probably central (one PO to supplier) even if stock sits in several warehouses. If so, the core aggregates demand network-wide for the *buy* decision but tracks position per warehouse for the *dashboard*. Confirm the buying reality before coding this - getting it wrong means either fragmented POs or wrong quantities.

### 5.6 Classification (drives confidence, not the maths directly)

ABC by annual consumption value; XYZ by demand coefficient of variation. Stored in `item_classification`. Stable A/X items → high confidence, candidates for low-touch. Erratic C/Z items → always human judgment. This gates what the founder is asked to look at.

### 5.7 Cash constraint (the layer that makes it Sorento-specific)

After the per-SKU quantities are computed, if `sum(cash_impact) > purchasing_budget` for the period:

1. Score each triggered SKU by urgency (how far below ROP / days-of-cover) × margin.
2. Allocate budget down the ranked list until exhausted.
3. Items that don't fit are shown as **deferred**, not dropped - with their stockout risk visible.

`GRILL 5.7` - is the ranking urgency×margin, or does the founder want a different priority (e.g. protect A-class service first, or protect key-customer SKUs)? This is a judgment encoding - get it from him, don't invent it.

---

## 6. Dashboard (Visibility layer - ship this first, it's the low-risk high-value win)

The dashboard alone, with **no recommendations**, mirrors what the founder computes in his head. It validates the data foundation and earns trust before the engine speaks.

**Per-SKU grid** (filter by warehouse, product class, colour, supplier, ABC/XYZ):
on-hand · on-order · committed · **net position** · avg daily demand · days-of-cover · ROP · status (OK / reorder-due / stockout / dead) · **cash tied up** · last movement date.

**Roll-ups:** total cash in stock · cash in dead stock (trapped) · SKUs below ROP · SKUs in stockout · incoming POs timeline.

**Recommendation view** (Recommendation layer, second): triggered SKUs with recommended qty, cash impact, days-of-cover, confidence band, LLM explanation, and **Accept / Adjust / Dismiss**. Adjust opens the override capture (§3.2 `recommendation_override`).

`GRILL 6.1` - stack: is this a React front-end reading a Postgres API, or served through the existing platform? What's the existing dashboard tech so this matches rather than introduces a new stack?

---

## 7. LLM boundary (write this down so it can't drift)

The LLM does exactly three things:
1. Turn a computed recommendation into a plain-language explanation ("Ordering 240 units - 6 weeks cover at current demand, lead time 5 weeks, you're 1 week from stockout").
2. Draft PO text / supplier message.
3. Answer natural-language questions about the *displayed* numbers.

The LLM is **given** net_position, ROP, qty, cash_impact as structured input. It has **no tool and no path** to compute or change them. Routing/trigger/quantity logic lives in code, keyed on data - never in a prompt. No example-overfitting: if the explanation template needs examples, they pin format only, never numbers.

`GRILL 7.1` - confirm there is no code path where an LLM output feeds back into a quantity field.

---

## 8. Build sequence (milestones - each independently demoable)

| M | Deliverable | Demo proof |
|---|---|---|
| **M0** | Schema + seed script; source-decoupling contract; read-model views | Tables populated from existing base + seed; core queries hit views only |
| **M1** | Net position + Visibility dashboard (no recommendations) | Founder sees his mental model on screen; net position reconciles to reality |
| **M2** | Classification + demand model (forward `demand_event` capture live) | ABC/XYZ populated; unmet-demand events logging from day one |
| **M3** | Reorder core: trigger + quantity + `reorder_policy` resolution | Given seeded data, engine flags the right SKUs with correct qty; policy change alters output with no code change |
| **M4** | Cash constraint + recommendation view + override capture | Budget cap reshuffles recommendations; override writes to `recommendation_override` |
| **M5** | LLM explanation layer | Each recommendation gets prose; numbers unchanged by the LLM |
| **Later** | AutoCount sync writes into the same tables | Core/dashboard unchanged; only `source_system` flips to `autocount` |

M1 is the PoC demo floor. M1 - M4 is the honest "co-pilot" demo. Ship M0 - M2 with forward capture live even if the demo only needs M1, because the demand signal is only valuable as it accumulates.

---

## 9. Test strategy

- **Golden-set fixtures** (your regression instinct): a seeded dataset with hand-computed expected ROP, SS, net position, qty for a dozen representative SKUs (one per ABC/XYZ cell, one multi-warehouse, one in stockout, one dead, one with an open PO). Fixtures in git. Engine output asserted against them in CI (self-hosted runner). Any formula change that moves a golden number fails the build until the number is re-blessed.
- **Decoupling test:** a test that fails if the core imports/queries anything AutoCount-shaped.
- **Censored-demand test:** seed a stockout window; assert the forecast excludes/imputes it rather than reading zero demand.
- **Override-integrity test:** an override never mutates the original recommendation row; it writes a linked override row.

---

## 10. Consolidated GRILL targets (hand these to `/grill`)

1. `3.1` Colour-variant granularity - SKU row or attribute? Decides forecast level.
2. `3.1` Stock ledger depth and append-only integrity - caps forecast history and stockout reconstruction.
3. `3.2a` Does SO data distinguish delivered vs pending per line? If not, committed (and net position) is unreliable.
4. `3.2b` Quotation table - build now (scaffold) or fully defer?
5. `3.2c` Purchasing budget - per month / per supplier / global? Who sets it?
6. `4.1` Forecast method - moving average for PoC, agreed? Or is there a demand pattern (seasonality, project lumpiness) that breaks it?
7. `4.2` Censored demand - forward capture only for PoC, reconstruction as fast-follow?
8. `4.3` Dead stock definition - no-movement-in-N-days vs turnover ratio?
9. `5.3` Safety stock - start fixed_days, expose statistical? Do we have clean σ?
10. `5.5` **Multi-warehouse buying reality** - central buy vs per-warehouse? Highest-impact unknown.
11. `5.7` Cash allocation priority - urgency×margin, or a different judgment ranking from the founder?
12. `6.1` Dashboard stack - match existing platform or new React app?
13. `7.1` Confirm no LLM-output-to-quantity path anywhere.
14. Overall: does M1 (Visibility only) satisfy the PoC demo, letting M3+ be built on trustworthy accumulated data rather than rushed for the demo?

---

## 11. What I'm assuming, that you should challenge

- The existing `stock_ledger` is rich enough to derive consumption and reconstruct historical on-hand. If it isn't, M2 shrinks to forward-capture only and the forecast is thin until data accrues.
- Sorento buys centrally per supplier even with multiple warehouses. If buying is genuinely per-warehouse, §5.5 changes materially.
- The founder will accept a transparent moving-average forecast he can follow over a more accurate model he can't. Trust is the adoption constraint, not forecast error.
- "Optimum stock" is expressible as a cash-vs-service-vs-dead-stock trade-off. If the founder's real objective function is different, the ranking in §5.7 is wrong and must be re-derived from him.
