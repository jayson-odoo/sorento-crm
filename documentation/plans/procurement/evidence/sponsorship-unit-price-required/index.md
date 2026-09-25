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

## Round 2 retake (review round 2, Blocking 1 + Should fix 2)

The four system screenshots below were retaken after the round 2 fix
(`FormMessage className="whitespace-normal"` on the U/P cell in both
`PurchaseRequestForm.tsx` and `PurchaseRequestDocumentEditCard.tsx`): the
resizable DataGrid's cell carries a `truncate` class (`overflow: hidden` plus
an inherited `white-space: nowrap`) that cut "Unit price is required." to
"Unit price is requir" in the round 1 screenshots. All four now show the full
sentence, wrapped onto two lines. The portal screenshots are unchanged from
round 1 (reviewer round 2 confirmed the portal table already wraps at both
widths - it is a plain `<table>`, not a resizable DataGrid, so it never had
the `truncate` class).

Every system screenshot below carries a Next.js dev-mode "1 Issue" badge in
the bottom-left corner. Opened once (via "Open issues overlay") to identify
it: a React console warning, "Each child in a list should have a unique 'key'
prop. Check the render method of `Demo1Layout`." `Demo1Layout` is the shared
app shell (sidebar/menu chrome) - not a file this PR or its round 2 fix
touches - so this is a pre-existing dev-only warning, unrelated to this diff.
It does not appear in a production build (dev-only overlay) and is left as
found.

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
  code + quantity with no unit price and clicking "Create" - shows the full
  "Unit price is required." inline message on the line, wrapped onto two
  lines, not clipped. Dev-mode "1 Issue" badge bottom-left (see above).
- `system-create-375.png` - 375px. Same blocked-create state at mobile width,
  scrolled so the `U/P *` column and the full inline message are in frame.

## System edit (`/procurement-management/sponsorship-forms/<id>/edit`)

- `system-edit-1280.png` - 1280px. Edit page for the seeded draft (opened via
  its Detail page's "Edit" button - same URL, in-place edit mode per the
  view/edit-same-layout convention), `U/P *` required column header, after
  clicking "Update" with the line's unit price left empty - shows the full
  "Unit price is required." inline message, wrapped, not clipped.
- `system-edit-375.png` - 375px. Same blocked-update state at mobile width,
  scrolled so the `U/P *` column and the full inline message are in frame.

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

The round 2 retake used a fresh throwaway sandbox (new admin user, new
`tenant_modules` rows, same deviation as above) and located the seeded row
via the list's own Search box (`ZZEVID-SP-ROUND2`) rather than scrolling the
unfiltered list - still sidebar/UI clicks throughout, no deep URL.
