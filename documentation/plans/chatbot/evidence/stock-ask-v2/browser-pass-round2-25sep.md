# Browser pass, round 2 fix round (PR #1221, 25 Sep 2026)

Closes round 2 reviewer pass Should fix 2 ("Reviewer pass round 2: PR #1221 at 99d9670c"):
AC-SA111 needed a 375px pass showing the CategoryForm modal reaching Save and the product
form placeholder, and AC-SA205's toggle needed a reload-persistence walk against the real
backend (neither existed on the branch; `browser-pass-phase1-24sep.md` was Phase 1 only,
against in-memory overlays).

Environment: this session's own sandbox, not a laptop lane. Bootstrapped Postgres with
`scripts/cloud-env-setup.sh` (from `origin/main`), which resolved SQLAlchemy 2.0.54 - already
within the repo's `<2.1` pin, so no manual pin was needed. Booted backend
(`venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000`), the RQ worker (`worker.py`), and
the frontend (`npm run dev`, Turbopack) against that same database. Seeded one admin login,
one UOM, one Respond contact, and enabled every module for the default tenant (a fresh
`bootstrap_env` schema installs no `TenantModule` rows, so the sidebar renders empty until a
tenant module row exists - same "cloud-lane bootstrap gap" the round 1 fix comment named, not
a code defect). Verified with `agent-browser` (headless Chromium at
`/opt/pw-browsers/chromium-1194`), driven by sidebar clicks from `/`, never a deep URL.

## AC-SA111: CategoryForm modal reaching Save, product form placeholder

### 1280px

- `open http://localhost:3000` -> signed in -> sidebar: Products > Reference Data > Product
  Categories (`/master-data-management/product-categories`).
- Clicked "Create Category". Filled Category Code `ZZT-RND2-1280`, Category Name
  `ZZT Round2 CategoryForm 1280`, Max quantity (assistant) `25`, ETA offset (days) `3`.
  Screenshot: `ac-sa111-categoryform-modal-1280.png` (not committed - see "Screenshot count"
  below; kept locally, described here instead).
- Clicked "Create". Network: `POST http://localhost:8000/api/v1/master-data/product-categories`
  -> `201`. The new row appeared in the list immediately after
  (`GET .../product-categories/tree` refetch), Active/Searchable badges both green.
- Sidebar: Products > Products > All Products (`/master-data-management/products`) > "Create
  Product" (`/master-data-management/products/new`). Filled Product Code
  `ZZT-RND2-PRD-1280`, Product Name `ZZT Round2 Product 1280`, Category = the category just
  created (X=25, Y=3). Switched to the Specifications tab: "Max quantity (assistant)" showed
  placeholder `25`, "ETA offset (days)" showed placeholder `3`, both inputs empty (no explicit
  override) - the R2 inherit-from-category contract, confirmed against the real Postgres
  columns via `GET .../master-data/categories/{id}` -> `chatbot_max_qty: 25,
  chatbot_eta_offset_days: 3`.
  Screenshot: `ac-sa111-productform-placeholder-1280.png` (kept locally, not committed).

### 375px

- `set viewport 375 812`, reload from `/`. Opened the sidebar drawer via the hamburger
  ("Toggle sidebar"), same click path: Products > Reference Data > Product Categories.
- Clicked "Create Category". The modal renders full-width, single column (Category Code,
  Category Name, Description, Display Order, Max quantity / ETA offset stacked, Active / Chat
  searchable switches, Cancel/Create) - no clipping, no horizontal scroll. Filled Category Code
  `ZZT-RND2-375`, Category Name `ZZT Round2 CategoryForm 375`, Max quantity `25`, ETA offset
  `3`.
  **Screenshot committed: `ac-sa111-categoryform-modal-375.png`** - this was the exact gap the
  round 2 reviewer flagged (no 375px "modal reaches Save" evidence existed).
- Clicked "Create". Network: second `POST .../master-data/product-categories` -> `201`. Both
  categories (`ZZT Round2 CategoryForm 1280` and `375`) now list on the page.
- Sidebar (drawer): Products > Products > All Products > "Create Product". Filled Product Code
  `ZZT-RND2-PRD-375`, Product Name `ZZT Round2 Product 375`, Category = `ZZT-RND2-375` (X=25,
  Y=3). The tab bar overflows at 375px, so the Specifications tab is reached via the "Scroll
  tabs right" control (`aria-label`d, keyboard/AT-reachable) before clicking it - not a hidden
  or unreachable tab. Scrolled the panel down: "Max quantity (assistant)" placeholder `25`,
  "ETA offset (days)" placeholder `3`, same inherit-from-category behaviour as 1280px.
  Screenshot: `ac-sa111-productform-placeholder-375.png` (kept locally, not committed).

## AC-SA205: contact toggle survives a reload

- Sidebar: Users & Access > People > "Internal Users" (`/user-management/contact-access-agents`,
  the contacts list - the nav label differs from the permission slug's "contacts" but the route
  and `user_management.contacts.view` gate are the same one AC-SA203 tests). One seeded contact
  (`+60000000001`, "ZZT Round2 Contact") listed.
- Clicked into it -> `/user-management/contacts/{id}` -> Access tab -> Chatbot card. "Notify
  salesman" was OFF (the seeded default, matching the model's `server_default=false`).
- Clicked the switch. Toast: "Chatbot settings saved". Switch now ON.
- `reload` (full page reload, not a client-side refetch) on the same
  `/user-management/contacts/{id}/access` URL. After reload: "Notify salesman" switch reads
  `checked=true` in the accessibility snapshot - the value round-tripped through the real
  `notify_salesman` column, not local component state.
  **Screenshot committed: `ac-sa205-notify-salesman-reloaded-still-on.png`.**

## Screenshot count

Per `documentation/agents/browser-verification.md` ("At most two screenshots per lane, each
under 200 KB"), only the two screenshots that close a gap the round 2 review named outright are
committed: the 375px CategoryForm-modal-reaching-Save shot and the AC-SA205 reload shot. The
1280px CategoryForm save and both product-form placeholder checks are recorded above as a text
log (steps, URLs, network calls and outcomes) instead of additional PNGs - the same trade this
lane's Phase 1 evidence document already made. `s1-product-form-placeholder-inherit-1280.png`
and `s2-contact-chatbot-toggles-375.png` from the Phase 1 pass stay as they are; they cover a
different pair of checks (S1's placeholder inherit and S2's toggle render, both pre-fix-round,
against the mock overlays that have since been deleted) and are superseded in substance, not
in file, by this document.

## Result

Every check the round 2 reviewer listed as open (AC-SA111 at 375px for both the CategoryForm
modal and the product form placeholder; AC-SA205's reload) passed against the real backend and
the real Postgres columns, at both 1280px and 375px where asked. No console errors or network
failures were observed during the walk (`console` / `errors` checked after each interaction).
