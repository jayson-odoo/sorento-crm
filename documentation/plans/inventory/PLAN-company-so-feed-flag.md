# PLAN: per-company "AutoCount sales orders connected" flag gates the chatbot's Outstanding

Status: Phase 2 (backend + frontend, test-first) - 9 Sep 2026
Lane: `.claude/worktrees/company-so-feed`, branch `feat/company-so-feed-flag`, base `origin/main`
UAC: `company-so-feed-flag-acceptance-criteria.md` (alongside)

## Journey

The chatbot's stock answer prints `*Outstanding:* N` under every warehouse row (D1, owner
console pass 8 Sep). Mocha has no sales orders in the CRM yet - its AutoCount SO feed is not
connected - so every Mocha row prints `Outstanding: 0`, which reads as "nothing on order"
when the truth is "we do not know". The owner wants Mocha rows to carry no Outstanding at all
until the feed lands, switched from the Companies admin page.

## Evidence (measured on origin/main, 9 Sep)

- `companies` rows: `MOCHA` / Mocha, `SRT` / Sorento. Both active, `autocount_ref` empty.
- `sorento_crm_backend/app/api/v1/inventory/stock.py::_with_sellable` attaches `open_so_qty`
  + `sellable` per detailed row (keyed `(product_id, warehouse_id)`), per compact
  `stock_summary` entry (product total) and per compact location line (`open_so_qty`),
  only under `include_sellable=true`.
- `sorento_crm_mcp/sorento_crm_mcp/presenters.py::_stock` appends `("open_so_qty",
  "Outstanding", ...)` ONLY when `s.get("sellable") is not None`; `_stock_compact` prints
  `(O/S: n)` from `open_so_qty` on the entry / location the same way. So a backend that
  simply does not attach the keys makes the presenter byte-identical to the pre-D1 shape.
  No MCP change.
- `Stock` and `Product` are `CompanyScopedMixin` (`company_id` column). `StockResponse`
  already serializes `company_id`.
- Companies admin: `app/api/v1/system/companies.py` (`CompanyForm`, `_serialize_company`),
  FE `app/(protected)/system-management/companies/` (form dialog with `Switch` for
  `is_active`, zod schema, `Company` type, `CompanyTable` columns).

## Simplest thing that works

One boolean column on `companies`. No settings table, no per-tool flag.

`companies.so_feed_live` (`Boolean NOT NULL DEFAULT true`, server_default `true`).
Migration `495_company_so_feed_live` (down_revision `494_from_so_external_link`): add the
column, then `UPDATE companies SET so_feed_live = false WHERE code = 'MOCHA'`. Downgrade
drops the column.

Sorento stays true so nothing changes for it. When Mocha's AutoCount SO ingest lands, an admin
flips the switch; no deploy.

## Slices (one PR, slices = commits)

### S1 backend (test-first)

- `app/models/company.py`: `so_feed_live = Column(Boolean, nullable=False, default=True,
  server_default="true")`.
- migration 495 as above.
- `app/api/v1/system/companies.py`: `CompanyForm.so_feed_live: bool = True`; create/update
  write it; `_serialize_company` emits it. This route is the manual dict builder - the
  lesson "a new DB column must be added to BOTH manual dict builders" applies here.
- `app/services/inventory_service.py::StockService`: new
  `companies_without_so_feed(company_ids: list[str]) -> set[str]` (one query on
  `Company.so_feed_live.is_(False)`), and `company_id_by_product(product_ids) -> dict[str,
  str]` (one query on `Product.company_id`).
- `app/api/v1/inventory/stock.py::_with_sellable`: compute the "no feed" company set once
  from the rows' `company_id` plus the products' companies. Skip `_attach` (and the
  location `open_so_qty`) for any detailed row, summary entry or location whose company
  is in that set. Also skip those products when synthesising the detailed-mode
  `stock_summary`, so a Mocha product gets no summary entry with `open_so_qty`. A row that
  is skipped carries NEITHER `open_so_qty` NOR `sellable` (the presenter's gate is
  `sellable is not None`).
- Tests: extend `tests/test_stock_sellable.py` (Postgres, `blank_session`, seed a Company
  with `so_feed_live=False` and one with `True`; product + stock scoped to each) and add
  `tests/test_companies_so_feed_live.py` for the route round-trip (create with flag false,
  update to true, list serialises it). Mirror the MCP side with one presenter test in
  `sorento_crm_mcp/tests/test_presenters_stock.py`: a row with no `sellable` key renders no
  `Outstanding` field (regression pin, not new behaviour).

### S2 frontend (HMR, browser verified)

- `types/company.types.ts`: `so_feed_live: boolean` on `Company` and `CompanyFormData`.
- `forms/company-schema.ts`: `so_feed_live: z.boolean()`.
- `CompanyFormDialog.tsx`: a `Switch` row "AutoCount sales orders connected" directly above
  the Active switch; default `true` on create, from the row on edit; sent on submit.
- `CompanyTable.tsx`: column "SO feed" (Yes / No badge, explicit `size`) between
  "AutoCount Ref" and "Users".
- `lib/companyMock.ts`: add the field to the mock rows so the type compiles.
- vitest: extend the existing companies component test (or add
  `CompanyFormDialog.test.tsx`) - edit dialog shows the switch reflecting the row, submit
  payload carries `so_feed_live`.

### S3 review + PR

`/code-review` (reviewer on Opus), then PR. Never merge; owner merges. After deploy the
migration already flips Mocha; owner verifies "MWC7625-SH-P" stock answer shows no
Outstanding on Mocha rows and still shows it on Sorento rows.

## Out of scope

- Deriving the flag from data (zero open SO is indistinguishable from "no feed").
- Hiding the SO/DO order tools for Mocha (different question; they already return nothing).
- The n8n side. The presenter is the only renderer and it is already gated on `sellable`.
