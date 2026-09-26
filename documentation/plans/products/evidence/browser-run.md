# Phase 3 browser verification - lane #1286 (product specifications for non-technical staff)

**Run date:** (this session). **Head verified against:** e4a46a20 (as given by the coordinator).
**Stack:** frontend `http://localhost:3000` (already running, not restarted), backend
`http://localhost:8000` against the cloud DB (migrated to `spec_0002`, per the coordinator).
**Tool:** `agent-browser@0.27.0`, session `lane1286`,
`AGENT_BROWSER_EXECUTABLE_PATH=/opt/pw-browsers/chromium-1194/chrome-linux/chrome`.
**Login:** the account configured under `E2E_EMAIL` / `E2E_PASSWORD` in
`sorento_crm_frontend/.env.local` (values never printed). Login itself succeeded (redirected
`/signin` -> `/`); the account's display identity, visible on-screen, is **"Demo Superadmin"**
(`demo.admin@sorentodemo.com`).

## Result: BLOCKED before any of the requested ACs could be exercised

Every AC in the brief (AC-S0.8, AC-S1.11-13, AC-S1.15, AC-S1.16 toast, AC-S2.1/2.5/2.8/2.10,
AC-S3.1-3.6) requires reaching **Products** or **Master data > Product Specifications / Brands**.
None of those are reachable from this account, by any in-app navigation path, at 1280 or 375.
No slice-specific screen was ever loaded, so there is nothing to report pass/fail on for the
individual ACs beyond "not verified - navigation blocked."

### What was tried, in order (sidebar-first, per the standing rule)

1. **Sidebar from `/`.** Logged-in home page (`/`, Dashboards) shows exactly two top-level items
   under "OVERVIEW": **Dashboards** and **Ideas**, plus the personalisation-only "Quick Access"
   group ("Pin menu items or folders for quick access", currently empty). No Products, no Master
   data, no System Settings, no other module of any kind.
   Screenshot: `evidence/blocked-sidebar-dashboards-ideas-only-1280.png`.
2. **"Switch layout" panel (top bar, apps-grid icon).** Opens a "Quick links" flyout listing
   Dashboard, Delivery Orders, **Products**, Internal Users, AI Agents, Permissions, Roles,
   Complaints, Integration Logs, Smart Linkage. Clicking **Products** in this panel does **not**
   navigate - the URL stays at `/` and the panel stays open. This reads as an "add to quick
   access" style picker/template artifact, not a real navigation surface: none of its entries
   moved the browser anywhere in three separate attempts.
3. **"Add shortcut" under Quick Access** (the RBAC-scoped pin-a-menu-item search). Typing
   anything returns only **Dashboards** and **Ideas** as candidates - this is the same list the
   real sidebar shows, confirming the two items above are the account's actual permitted menu,
   not a rendering glitch.
4. **Global "Search menu..." (Ctrl+Shift+K).** Empty-state suggestions: Dashboards, Ideas only.
   Typing `product` returns an **empty** results list - no suggestion at all, for any string
   containing "product". Screenshot: `evidence/blocked-search-menu-no-product-results-1280.png`.
5. **Network check.** `GET /api/v1/user-management/users/me/permissions`,
   `GET /api/v1/system/modules/me` and `GET /api/v1/master-data/products?...` were all observed
   returning `200` in the page's own request log at various points (most likely Next.js `<Link>`
   prefetch from step 2's flyout rendering, not an actual navigation - the URL never changed and
   no product list ever rendered on screen). So the backend is not flatly refusing this principal;
   the **frontend's own menu/search index has nothing under "product" or "master data" for this
   account**, which is what actually blocks every requested AC (all of them are screens reached
   through that index).
6. **Company switcher.** The "Sorento SRT" badge in the top bar is not interactive (no dropdown) -
   single-company install, not a wrong-company-context explanation.

### Why this reads as an environment/demo-data gap, not a code defect in this lane

The account is literally named **"Demo Superadmin"**. CLAUDE.md documents a backend short-circuit
("the guard short-circuits when... the user has superadmin/admin"), so if this account's role
carries an `is_superadmin`/`admin` marker the backend module guard would already be waived - which
is consistent with the `200`s in step 5. But the **frontend nav-config / search index** apparently
still filters on explicit permission slugs (or on which modules are enabled for this tenant), and
whatever seeded this cloud DB's demo tenant did not grant this role - or enable the
`master_data`/`products` module for this tenant - beyond Dashboards and Ideas. Lane #1286 does not
touch RBAC seeding, module enablement, or nav-config, so nothing in this lane's diff plausibly
caused this; it looks like the cloud demo environment itself is missing a grant or a module-enable
row that a normal admin account would have.

I did not attempt to fix this myself: granting permissions or enabling modules against the shared
cloud DB is outside a browser-verification pass's remit, is not reversible by me, and is not
something the coordinator's message authorised. Recommend one of:

- Grant this "Demo Superadmin" role (or the E2E account specifically) the
  `master_data.products.view`/`.edit`, `master_data.spec_registry.view`/`.edit`/`.add` permission
  slugs (and confirm the `master_data` module is enabled for this tenant if module rows exist), or
- Supply a different login that already has them, or
- Re-run `seed_spec_registry` / whatever RBAC seed migration normally grants these to an admin role
  on this cloud DB, since it appears to be missing beyond Dashboards/Ideas.

## Per-AC status (all screens unreachable)

| AC | Status | Note |
| --- | --- | --- |
| AC-S0.8 | NOT VERIFIED - blocked | Products list / product Specifications tab / Brands form unreachable |
| AC-S1.11 | NOT VERIFIED - blocked | Spec record tabs unreachable |
| AC-S1.12 | NOT VERIFIED - blocked | Details tab unreachable |
| AC-S1.13 | NOT VERIFIED - blocked | How it is read grid / rule modal unreachable |
| AC-S1.15 | NOT VERIFIED - blocked | Choices and words grid unreachable |
| AC-S1.16 (toast) | NOT VERIFIED - blocked | Cannot save a rule without reaching the spec record page |
| AC-S2.1 / S2.5 / S2.10 | NOT VERIFIED - blocked | Product Specifications tab unreachable |
| AC-S2.8 | NOT VERIFIED - blocked | SRTWC7604-SC-SH page unreachable |
| AC-S3.1 - S3.6 | NOT VERIFIED - blocked | Product Specifications list / record page unreachable |

## Evidence

- `evidence/blocked-sidebar-dashboards-ideas-only-1280.png` - the full sidebar at `/`, 1280px:
  only Dashboards and Ideas.
- `evidence/blocked-search-menu-no-product-results-1280.png` - global search for "product",
  empty result list.

No 375px pass was attempted - there is nothing to view at either width until navigation is
restored, and the standing rule is not to deep-link around a permission gate (that would hide,
rather than reveal, exactly this kind of nav/permission defect).

## Rule engine / other work not reached

Because no spec-record screen loaded, none of the following from the brief were attempted:
adding a Words rule on Finish or colour, the "Saved. N products updated." toast, or the deferred
delete countdown. These remain fully unverified in a real browser and should be re-run once the
account/module gap above is fixed.
