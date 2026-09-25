# Browser evidence: sponsorship unit price required (#1227 / PR #1232 review round 1, Should fix 3)

Captured with `agent-browser@0.27.0` (headless Chromium) against a locally-seeded
dev stack (backend `uvicorn` on :8000 against a scratch `sorento_ci` Postgres,
frontend `npm run dev` on :3000). All six screenshots are under 200KB.

Seed data (throwaway, not committed): one admin user with the `superadmin` role
(for the system screens), one `RespondContact` + verified `PortalToken` (for the
portal screen), and one `sponsorship_form` `PurchaseRequestHeader` in `draft`
status with a single `PurchaseRequestLine` that has `unit_price = NULL` on
purpose, so every screen can show the required-mark and the blocked-save state
without any manual field editing.

## Portal submit (dealer web portal, `/portal/sponsorship_form/<id>`)

- `portal-submit-1280.png` - 1280px. Items table with the `UNIT PRICE*` header,
  the empty unit price cell outlined in red, and the inline "Unit price is
  required." message, after clicking "Submit sponsorship form" (and confirming
  the "Submit this sponsorship form?" dialog) on the price-less seeded line.
- `portal-submit-375.png` - 375px. Same blocked-submit state, with the items
  table scrolled horizontally so the `UNIT PRICE*` column and the inline error
  are in frame (the table is wider than the viewport at this width).

## System create (`/procurement-management/sponsorship-forms/new`)

- `system-create-1280.png` - 1280px. New Sponsorship Form page, line items
  table with the `U/P *` required column header, after filling in an item
  code + quantity with no unit price and clicking "Create" - shows the
  "Unit price is requir[ed]" inline message on the line.
- `system-create-375.png` - 375px. Same blocked-create state at mobile width.

## System edit (`/procurement-management/sponsorship-forms/<id>/edit`)

- `system-edit-1280.png` - 1280px. Edit page for the seeded draft (opened via
  its Detail page's "Edit" button), `U/P *` required column header, after
  clicking "Update" with the line's unit price left empty - shows the "Unit
  price is requir[ed]" inline message.
- `system-edit-375.png` - 375px. Same blocked-update state at mobile width.

## Navigation path used (system screens)

Logged in via the real NextAuth credentials form at `/signin`, then sidebar:
Dashboards home -> "Project Sales Admin" group -> "Sponsorship Forms" ->
"Create" (for system create), and for system edit: "Sponsorship Forms" list ->
click the seeded row (`ZZEVID-SP-...`) -> Detail page -> "Edit" button. No deep
URLs were used to reach these screens; all navigation was by sidebar/UI clicks
from `/`, per `documentation/agents/browser-verification.md`.

One deviation was required to make the sidebar's "Project Sales Admin" group
(and every other module-gated group) render at all: this sandbox's Postgres
had zero `tenant_modules` rows, which makes `GET /api/v1/system/modules/me`
report every module as `enabled: false` and the frontend's `useTenantModules`
filter the whole group out of the sidebar (the backend's own RBAC *guard*
separately treats "no module rows" as legacy/bypassed, per `CLAUDE.md`, but
that bypass does not extend to this frontend nav-visibility endpoint). All 22
catalog modules were enabled for the default tenant (`tenant_modules` rows
with `enabled=true`) as part of the throwaway seeding so the sidebar matched
what a normal installed tenant would show.
