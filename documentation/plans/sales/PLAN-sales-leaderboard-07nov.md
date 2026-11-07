# PLAN: SALES-LEADERBOARD (sales leaderboard screen)

Status: Build (owner 7 Nov ~16:15 "2227 ok": Q1-Q5 all (a)). Phase 1 FE against mocks + Phase 2 tester red tests. Track: full (size L, new screen; new permission slug = migration).
code until the owner answers. Track: full (size L, new screen; new permission slug = migration).
Card: `CARD-sales-leaderboard-07nov.md`. UAC: `sales-leaderboard-07nov-acceptance-criteria.md`.
Mockup: `mockups/sales-leaderboard-07nov.html` (real October figures, dev copy `sorento_prod_1104`).
Evidence SQL: `evidence/sales-leaderboard-oct-dev.sql` (run), `evidence/sales-leaderboard-line-vs-doc-dev.sql` (run).

Owner 7 Nov ~15:40: "I also need a sales leaderboard feature. So let's think about it."

Fixed inputs:
- Sales = IV + CS + DN - CN net, by DocDate, not cancelled (owner 27 Oct, SALES-UNIFIED).
- One sales calculator: the REPORT-UNIFY engine (`services/reports/ask.run_ask`, invoiced basis). No second one.
- Targets / tiers / commission exist; a salesperson sees only their own commission. The board shows none.

## Open before build
1. ~~Owner answers card Q1-Q5~~ answered 7 Nov ~16:15: all (a).
2. ~~Line sum vs header total~~ settled 7 Nov (comment 6704254640): a blank-item SUBTOTAL line double counted by the
   line sum; header right. Fixed in the shared query by lane SALES-SUBTOTAL-LINES; this lane inherits it, no
   workaround. Dependency: the board's reference test (UAC L2-3) passes only once that lane is on main; rebase then.


## Contract (Phase 1, binding for FE mock, tests and BE)

`GET /api/v1/sales/leaderboard` (sales module guard; `sales.leaderboard.view`, else 403 `PERMISSION_DENIED` as
`require_permission`). Query: `date_from` (YYYY-MM-DD, required), `date_to` (required, >= date_from, else 422
`REPORT_INVALID_PARAMS`), `company` (company id, optional, must be in the user's grants else 403), `brand` (ids,
repeatable, optional), `category` (ids, repeatable, optional), `previous_from` + `previous_to` (optional, both or
neither, else 422 `REPORT_INVALID_PARAMS`; previous_to >= previous_from, else 422). The period chips send them (this
month: same days of last month; last month: the month before; this quarter: same days of the previous quarter; YTD:
same dates last year); absent, the window is `ask.compare_window("previous_period", ...)` (Custom).

```json
{
  "date_from": "2026-10-01", "date_to": "2026-10-31",
  "previous_from": "2026-09-01", "previous_to": "2026-09-30",
  "as_of": "2026-11-04T03:10:00" ,
  "total": {"amount": 16369803.26, "prev_amount": 15894544.36, "change_pct": 3.0},
  "no_agent_amount": 1210.32,
  "rows": [
    {"rank": 1, "person": "LCL", "codes": ["LCL"], "amount": 1856856.61, "prev_amount": 1135260.82,
     "change_pct": 63.6, "customers": 24, "is_me": false}
  ],
  "me": {"person": "JENNIFER", "rank": 20}
}
```
- `previous_*`: as sent, else `ask.compare_window("previous_period", date_from, date_to)` (same number of days just
  before: Oct 1-31 gives Aug 31-Sep 30, which is why the chips send their own window).
- `total`: the whole period incl. no-agent sales (= the Sales & outstanding Invoiced total); `change_pct` null when
  `prev_amount` <= 0. Same rule on every row.
- `rows`: persons with a non-zero amount in the period (a negative person stays listed), ranked by amount desc, ties by person name; `rank` dense
  1..n; no "(no agent)" row (its amount is `no_agent_amount`, 0.0 when none). `codes`: the agent codes, sorted,
  that sold in the period for that person. `customers`: distinct customers invoiced across the person's codes.
- `me`: when the caller's user is linked to agents (`own_scope.me().agent_ids`) whose person is on the board, its
  person + rank (the best-ranked when the user's agents are several persons); else null. `is_me` true on that row.
- `as_of`: `max(billing_documents.last_synced_at)` over all the caller's granted companies, ignoring the `company`
  filter (null when none); naive UTC.
- Money as JSON numbers with 2 decimals; `change_pct` 1 decimal.

`GET /api/v1/sales/leaderboard/options` (same permission): `{"companies": [{"value": id, "label": code}],
"brands": [{"value","label"}], "categories": [{"value","label"}]}`. Companies = the caller's grants.

Engine: `sales_person` dimension on the invoiced ask only (`ask.CATALOGUE["sales"]["invoiced"]["dimensions"]`),
column in `billing_document_lines.ASK_COLUMNS`: `coalesce(sales_agents.person_label, inv.agent_label())`, NULL ->
`inv.NO_AGENT`. `crm_report_ask` route accepts `group_by=sales_person` on `basis=invoiced` (422 `unknown_group_by`
on other bases, unchanged).

Permission `sales.leaderboard.view` ("View the sales leaderboard", "Open Sales > Leaderboard: invoiced sales ranked
by sales person. Shows no commission."): registry entry + insert-only guarded migration granting it to admin and
superadmin (precedent `alembic/versions/sales_s1_reports_module.py`).

## Design (on the recommended options; paths under `sorento_crm_backend/app/` unless marked)

### Backend
- **`sales_person` dimension** on `services/reports/datasets/billing_document_lines.py` `COLUMNS` and the invoiced
  `ASK_DEFINITION` dimensions (`ask.py:36,56-61`): `coalesce(sales_agents.person_label, agent code)` over
  `inv.agent_id()`, NULL (the "(no agent)" row) when there is no agent. One label expression, next to
  `inv.agent_label()` (`services/sales/invoiced_sales.py:134`). Codes per row: a second text column
  (`string_agg(DISTINCT code)`), read by the board only.
- **Route** `GET /api/v1/sales/leaderboard` in a new `api/v1/sales/leaderboard.py` (mounted with the sales router):
  query `date_from`, `date_to`, `company`, `brand`, `category`. Calls `run_ask(dataset="sales", basis="invoiced",
  measure="amount", group_by="sales_person", top_n=1000, also=("customers",))` (assumed, not verified: that `also` carries a distinct-count measure; if not, a second `measure="customers"` run joined by name) and the same for
  `ask.compare_window("previous_period", ...)`, then `ask.attach_compare`. Company grants = the user's switchable
  set (as `api/v1/reports/reports.py:87-94`). Lifts the "(no agent)" row out of the ranking into `no_agent`. Blanks
  `change_pct` when the previous figure is <= 0 (leaderboard layer only; the chatbot keeps its own rule).
  Adds `me` = the person label of the user's agent (`services/own_scope.me()`, `own_scope.py:104-114`) when linked.
  Adds `as_of` = `max(billing_documents.last_synced_at)` in the granted companies.
- **Permission** `sales.leaderboard.view`: `app/rbac/permission_registry` entry + insert-only guarded migration
  (precedent `alembic/versions/pp2_0001_view_own_perms.py`), granted to no role by the migration; the owner grants it.
  Revision id <= 32 chars, re-parented with `scripts/alembic-reparent.sh`.
- **Assistant**: `crm_report_ask` route allow-list gains `group_by=sales_person` on invoiced
  (`api/v1/order_management/report_ask.py` group-by tuple); MCP catalog description line
  (`sorento_crm_mcp/sorento_crm_mcp/catalog.py:921-1000`); one eval line "who's top this month".

### Frontend (`sorento_crm_frontend/`)
- `app/(protected)/sales/leaderboard/page.tsx` + `components/LeaderboardView.tsx`, `LeaderboardPodium.tsx`.
- `services/salesLeaderboardService.ts` -> `lib/api-client`; `hooks/useSalesLeaderboardQuery.ts`.
- Reuse: `components/common/PageHeader.tsx`, `components/reports/ReportFilterBar.tsx` period chips (or its chip
  part), `components/ui/date-range-picker.tsx`, `components/scm/StatCard.tsx`, `components/ui/data-grid*.tsx`,
  `components/ui/badge.tsx`, SearchableSelect.
- Menu: `config/menu.config.tsx` Sales group after Sales Teams, gated by `sales.leaderboard.view`.

## Test list (Phase 2, tester first)
- pytest: board total == Sales & outstanding invoiced total (same period / company); person grouping merges codes
  across companies; no-agent row out of the ranking; cancelled excluded, CN subtracts; change blank on prev <= 0;
  403 without `sales.leaderboard.view`; company grants respected; `me` set only for a linked user;
  `crm_report_ask` `group_by=sales_person` returns the board's rows.
- vitest: podium with 1/2/3 rows, own-row highlight, empty state, change formatting.
- Browser: 1280 + 375, sidebar navigation from `/`.

## Not built (triggers)
- Team board: owner asks for one (needs a team dimension with dated stays).
- Target % column: the first invoiced agent target.
- New customers column: owner asks (no measure today).
- House-code exclude list: owner asks.
- Daily snapshot / history of ranks: owner asks for rank movement over time.
