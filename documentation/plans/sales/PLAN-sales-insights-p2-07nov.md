# PLAN: SALES-INSIGHTS-P2 (leaderboard phase 2: drilldown, perspectives, targets, customisable)

Status: Asked (card Q1-Q5 on PR #2231, evidence SQL with crew). Track: full (size L). Depends on #2230 (SALES-SUBTOTAL-LINES) for correct figures.
Parent: `PLAN-sales-leaderboard-07nov.md` (#2227, main 76afa03f).

Owner 7 Nov ~17:45: "I want to extend with more drilldown to see what's the item, customer of the sales agent, and
see from the customer perspective, product perspective, maybe merge with top selling product, and also how does it
compare with target, reuse our reporting and dashboarding tool so users have some customisability."

Card: `CARD-sales-insights-p2-07nov.md`. Evidence: `evidence/sales-insights-p2-oct-dev.sql` (dry-run clean on an empty migrated DB). No code before the owner answers the card.

## Open before build
1. Owner answers card Q1-Q5 (crew-ask on #2231, 7 Nov).
2. Crew runs `evidence/sales-insights-p2-oct-dev.sql`; the mockup and the UAC reference figures come from it.
3. Targets: Q5 of the evidence decides which target a person shows when several agent targets of one person cover
   the board's end date (FANNY I / III / IV each hold one; `achievement_service.label_siblings` credits each with the
   whole person, so they are not additive).
4. SALES-SUBTOTAL-LINES (#2230) on main before the reference tests (inherits the fix, as #2227).

## Contract draft (on the card's recommended options; rewritten once answered)

`GET /api/v1/sales/leaderboard` keeps every #2227 param and field, and gains:
- `basis` = `invoiced` (default) | `delivered` | `ordered` | `outstanding` (owner 7 Nov), passed to `run_ask(basis=...)`.
  Gate per basis: invoiced `sales.reports.view`, the others `order_management.orders.view`, except the person view
  (`sales.leaderboard.view` suffices, #2227 ruling). Outstanding: dates optional (`ask.OPEN_BASES`), `prev_*` and
  `change_pct` null.
- `channel` filter (repeatable; invoiced: `inv.SALES_TYPES` values, order bases: dealer / project / other) and
  `by=channel`. `/leaderboard/options` gains `channels` per basis.
- Customer rows carry `code` (customers.customer_code of the row's ids, comma-joined when a name spans two companies).
- `by` = `person` (default) | `customer` | `product` | `brand` | `category` | `channel`; anything else 422 `REPORT_INVALID_PARAMS`.
  It is `run_ask(group_by=...)`, `sales_person` for `person`.
- Drill filters, each repeatable: `person` (person labels, the new `sales_person` filter word), `customer` (ids),
  `product` (ids); `brand`, `category` as today. A drill chip is one of these.
- Access (Q2 a): `by != person`, or a `person` filter naming anyone but the caller's own person(s), needs
  `sales.reports.view` as well, else 403 `PERMISSION_DENIED`.
- Every row gains `name` (the grouped value) and `keys` (`run_ask`'s ids behind it, what a drill sends), `qty`, and on
  `by=customer|product|brand|category` the person row fields (`person`, `codes`, `is_me`) are absent.
  `customers` stays (distinct customers); `products` (distinct items) added for person/customer rows.
- Person rows gain `target`: null, or `{target_no, basis, metric: "amount", period_from, period_to, target_amount,
  achieved_amount, achieved_pct, like_for_like}` for the person's all-products amount agent target whose period holds
  `date_to`; `like_for_like` = basis invoiced and the period equals `date_from..date_to`. Figures from
  `target_periods.target_value` and `achievement_service.achieved_by_period`. No commission field, ever.
- `no_agent_amount` only on `by=person` (0.0 elsewhere).

Engine: `sales_person` dimension on the three order bases (one column each over `SalesAgent.person_label`); channel filter values on invoiced through `inv.normalise_sales_types` instead of `_CHANNEL_CLASS` (`ask.py:290`). `sales_person` filter word on every sales basis, first the invoiced ask (`ask.CATALOGUE["sales"]["invoiced"]["filters"]`, a
`SelectParam` on `billing_document_lines.ASK_DEFINITION` over `inv.person_label()`, options = person labels), so
`crm_report_ask` and the Sales & outstanding screen take it too; `sales_person` dimension unhidden on that screen.

FE: `LeaderboardView` gets the View by tabs + chip trail (URL state), drill on row click, Target column, Open as report
(`/sales/sales-and-outstanding?tab=invoiced&seed=<json>`; `ReportPage` reads `seed` once: params + pivot rows), Open in
Top selling items on the Product view, and Top selling items links back.

## Test list (Phase 2 draft)
- pytest: each `by` total == the person board total for the same period/filters; person drill == Sales & outstanding
  invoiced filtered by that person; a code AutoCount sent that is not a CRM agent drills by its label; 403 on
  `by=customer` without `sales.reports.view`; own-row drill allowed without it; another person's drill 403; target
  null when none, labelled when ordered/yearly, `like_for_like` on a monthly invoiced target; no key containing
  `commission`/`tier`/`rate` anywhere in the response; `crm_report_ask` with `sales_person` filter == the drill.
- vitest: view switch + chip trail round trip through the URL; drill from person to customers and back; target cell
  text per basis; Open as report seed; empty states per view.
- Browser: 1280 + 375, from `/` by sidebar.
