# PLAN: SALES-INSIGHTS-P2 (leaderboard phase 2: drilldown, perspectives, targets, customisable)

Status: Review done (reviewer READY, security CLEAN after fix round 1, 7 Nov); crew browser pass + owner hand test next
(`sales-insights-p2-handtest.md`). Was: Build (Phase 2). Owner 7 Nov: card + mockup v7 "Ok": Q1-Q5 all (a) + customer names, Channel filter / view,
basis switch; self-service option A (remember last setup) included. Track: full (size L). Track: full (size L). Depends on #2230 (SALES-SUBTOTAL-LINES) for correct figures.
Parent: `PLAN-sales-leaderboard-07nov.md` (#2227, main 76afa03f).

Owner 7 Nov ~17:45: "I want to extend with more drilldown to see what's the item, customer of the sales agent, and
see from the customer perspective, product perspective, maybe merge with top selling product, and also how does it
compare with target, reuse our reporting and dashboarding tool so users have some customisability."

Card: `CARD-sales-insights-p2-07nov.md`. Evidence: `evidence/sales-insights-p2-oct-dev.sql` (dry-run clean on an empty migrated DB). No code before the owner answers the card.

Mockup (approved v7): `mockups/sales-insights-p2-07nov.html`. UAC: `sales-insights-p2-07nov-acceptance-criteria.md`.
Evidence: `evidence/sales-insights-p2-oct-dev.sql` (rounds 1-2), `evidence/sales-insights-p2-round3-dev.sql` (round 3).

## Rulings (owner 7 Nov, "Ok" on card + mockup v7)
Q1 (a) Top selling linked both ways. Q2 (a) own-row drill for everyone; other views / other people need the basis
slug. Q3 (a) Target column labelled with the target's own basis + period, hidden while no row has one. Q4 (a) Open as
report into Sales & outstanding (saved views, sidebar star), no dashboard. Q5 (a) same screen, chips, URL state.
Plus: customer NAME (code underneath); Channel filter + View by; Basis switch Invoiced / Delivered / Ordered /
Undelivered from `run_ask`; option A remember the last setup (per browser).

## Contract (binding for tests, BE and FE)

`GET /api/v1/sales/leaderboard` (router guard unchanged: `sales.leaderboard.view`, else 403 `PERMISSION_DENIED`).

Query (every #2227 param keeps its meaning):
- `basis` = `invoiced` (default) | `delivered` | `ordered` | `outstanding`; else 422 `REPORT_INVALID_PARAMS`.
- `by` = `person` (default) | `customer` | `product` | `brand` | `category` | `channel`; else 422.
- `date_from` / `date_to`: required, except on `outstanding` where both may be absent (both or neither, else 422;
  absent = every date, `ask.OPEN_BASES`).
- `previous_from` / `previous_to`: as #2227; ignored on `outstanding` (no compare there).
- `company`, `brand` (repeat), `category` (repeat): as #2227.
- `channel` (repeat): sales type values. Invoiced: `dealer`, `project`, `other`, `set_apart`, `mixed`,
  `type_not_set`, `no_sales_order` (`inv.SALES_TYPES`). Order bases: `dealer`, `project`, `other`. Any other value on
  the basis: 422 `REPORT_INVALID_PARAMS`.
- Drill filters, each repeatable: `person` (person labels, as the board prints them), `customer` (customer ids),
  `product` (product ids).

Access (Q2). Let `slug(basis)` = `sales.reports.view` for invoiced, `order_management.orders.view` otherwise
(superadmin / admin pass, as `require_permission`). The caller needs `slug(basis)` UNLESS either
(a) `by=person` and no `person` / `customer` / `product` filter (the board itself, on any basis), or
(b) `person` is set and every value is one of the caller's own persons (`own_scope.me().agent_ids` -> person label).
Otherwise 403 `PERMISSION_DENIED`. `brand` / `category` / `channel` / `company` never need it.

Response:
```json
{
  "basis": "invoiced", "by": "person",
  "date_from": "2026-10-01", "date_to": "2026-10-31",
  "previous_from": "2026-09-01", "previous_to": "2026-09-30",
  "as_of": "2026-11-04T03:10:00",
  "total": {"amount": 16369803.26, "qty": 0, "prev_amount": 15894544.36, "change_pct": 3.0, "customers": 1075, "products": 0},
  "no_agent_amount": 1210.32,
  "rows": [
    {"rank": 1, "name": "LCL", "keys": [], "amount": 1856856.61, "qty": 0, "prev_amount": 1135260.82, "change_pct": 63.6,
     "customers": 24, "products": 684,
     "person": "LCL", "codes": ["LCL"], "is_me": false, "target": null}
  ],
  "me": {"person": "JENNIFER", "rank": 20},
  "can_drill_others": true
}
```
- `date_*` / `previous_*`: null when absent (outstanding all dates; previous always null on outstanding).
- `total`: `run_ask` total of the whole query (filters applied), `prev_amount` / `change_pct` null on outstanding;
  `customers` / `products` distinct counts (`also`).
- `rows`: `run_ask(group_by=<by>)` rows with a non-zero figure, ranked by amount desc then name, dense 1..n. `name`
  is the engine's row value; `keys` = `run_ask` row keys (customer / product / brand / category ids; `[]` for
  person). By `person`: as #2227 (`person`, `codes`, `is_me`, no "(no agent)" row, `no_agent_amount`) plus `target`.
  By `customer`: `code` (the customer codes of `keys`, sorted, ", "-joined) and `companies` (company codes, sorted).
  By `product`: `brand`, `category` (of the first key's product, null when none). By `channel`: `key` = the sales type
  value (`dealer`, ..., null for the order bases' "(none)" row).
  Every by except person: `no_agent_amount` 0.0, `me` null.
- `prev_amount` / `change_pct` per row: previous window joined by `name`, the #2227 rule (null when prev <= 0),
  both null on outstanding.
- `target` (person rows only, Q3): null, or `{"target_no", "basis", "period_from", "period_to", "target_amount",
  "achieved_amount", "achieved_pct", "like_for_like"}` for an AGENT target (`subject_kind = agent`) of any agent
  whose person is the row's person, `metric = amount`, `product_scope = all`, with a period
  (`target_periods`) holding `date_to` (today when absent) and `target_value > 0`. Several: the lowest
  `target_no`. Figures: `target_periods.target_value` and `achievement_service.achieved_by_period`;
  `achieved_pct` = `achievement_service.achieved_pct`. `like_for_like` = target basis == `basis` and the period is
  exactly `date_from..date_to`. Never a commission / tier / rate / payout key anywhere.
- `can_drill_others`: the caller holds `slug(basis)`.

`GET /api/v1/sales/leaderboard/options`: as #2227 plus `"channels": {"invoiced": [{value,label}...],
"delivered": [...], "ordered": [...], "outstanding": [...]}` (invoiced = `inv.SALES_TYPES` order; order bases
dealer / project / other with the same labels) and `"can": {"invoiced": bool, "delivered": bool, "ordered": bool,
"outstanding": bool}` (= holds `slug(basis)`).

### Engine (`app/services/reports/`)
1. `sales_person` DIMENSION on the delivered / ordered / outstanding definitions
   (`datasets/sales_order_lines_ask.py`): `coalesce(nullif(btrim(SalesAgent.person_label), ''), SalesAgent.sales_agent,
   NO_AGENT)`; `ask.CATALOGUE` dimensions for those three bases gain `sales_person` (pending_delivery / unpaid unchanged).
2. `sales_person` FILTER word on invoiced / delivered / ordered / outstanding: a `SelectParam("sales_person", ...)`
   on each definition over the same person expression (invoiced: `inv.person_label()`), options = distinct person
   labels; the four CATALOGUE entries' `filters` gain it. `crm_report_ask` accepts it on those bases
   (`api/v1/order_management/report_ask.py` allow-list) and the MCP `crm_report_ask` description names it.
3. Channel filter values per basis in `ask._params` (`ask.py:290`): invoiced -> `inv.normalise_sales_types` (all
   seven types); order bases -> `{dealer: retail, project: project, other: other}`, anything else 422
   `REPORT_INVALID_PARAMS` (today `_CHANNEL_CLASS[v]` raises KeyError for `other`).
4. Sales & outstanding: `sales_person` visible in the Rows picker on the four bases (invoiced `ASK_COLUMNS` no longer
   hides it) and as a filter.

### Frontend
- `LeaderboardView`: Basis chips (Invoiced / Delivered / Ordered / Undelivered orders; Undelivered adds an
  "All open" period chip, its default); View by line tabs (Sales person / Customer / Product / Brand / Category /
  Channel; the non-person tabs only when `options.can[basis]`); Channel multi-select (options per basis); drill chip
  trail (Badge + clear); row click drills (person -> customer, customer -> product, product / brand / category /
  channel -> customer); a row is clickable when `can_drill_others` or it is the caller's own person row; the whole
  state (basis, by, period, filters, chips with their labels) in the URL so Back and a shared link reproduce it;
  with no URL state the last setup from `localStorage` (try/catch; option A). Target column (hidden when no row has
  one): "<pct>% of <period>, <basis>", plain % when `like_for_like`, tooltip with target and achieved RM. Customer
  rows: name, code underneath, Companies column. Product rows: Brand, Category, Qty. "vs last period" blank on
  Undelivered.
- "Open as report": `/sales/sales-and-outstanding?tab=<invoiced|delivered|ordered|undelivered>&seed=<json>`;
  `ReportPage` applies a `seed` once (params: period, brand, category, channel, sales_person, customer, product;
  pivot rows = the board's by, cols `all`, measures `amount`, `qty`) instead of the default view, and drops it from
  the URL. Product view on Invoiced: "Open in Top selling items" (`/sales/top-selling-items?seed=...`, period /
  brand / category); Top selling items shows a "Product ranking" link back (`/sales/leaderboard?basis=invoiced&by=product`).
- `salesLeaderboardService` / `useSalesLeaderboardQuery` gain the params and fields above.

## Test list (Phase 2, tester first)
pytest (`tests/test_sales_insights_p2.py`, seeded Postgres world, no dev data):
- each `by` total equals the person-board total and `run_ask` total for the same basis / period / filters;
- every basis: board total == `run_ask(basis)` total; outstanding without dates == all-dates total, prev null;
- person drill: `person=X&by=customer` == run_ask customer rows filtered by X's codes; a person with two codes drills
  as one; a code AutoCount sent that is not a CRM agent drills by its code (invoiced);
- `sales_person` dimension + filter on delivered / ordered / outstanding;
- channel: by=channel rows carry the sales type `key`; the filter keeps only that channel; `other` works on every
  basis; `no_sales_order` on invoiced; `no_sales_order` on ordered = 422; unknown value 422;
- customer rows `code` + `companies`; product rows `brand` / `category`;
- access matrix: leaderboard.view only -> person board 200 on every basis, `by=customer` 403, other person drill 403,
  own person drill 200, `customer=` filter 403; + sales.reports.view -> invoiced all 200, delivered by=customer 403;
  + orders.view -> delivered 200; options `can` mirrors it; `can_drill_others` mirrors it;
- target: none -> null; RM 0 target -> null; ordered yearly target -> labelled, like_for_like false; invoiced monthly
  target on that month -> like_for_like true; lowest target_no wins; no key containing commission / tier / rate /
  payout / bonus anywhere in the body (recursive scan);
- bad basis / by / channel 422; outstanding with one date 422;
- `crm_report_ask` with `sales_person` filter on invoiced == the drill rows; existing #2227 tests still green (the
  two that pinned `sales_person` as invoiced-only are rewritten to the new rule).
vitest: URL round trip (basis, by, chips, period); drill person -> customer -> product and chip removal; tabs hidden
without `can[basis]`; own row clickable without it, others not; Target cell text (labelled / like for like /
column hidden); customer name + code; Undelivered: All open chip default, change blank; Open as report URL + seed;
ReportPage applies a seed; localStorage restore when the URL is empty (and survives a throwing storage).
Browser (crew): 1280 + 375 from `/`.
