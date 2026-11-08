# SORENTO-TOWN browser evidence (head b8f9f70db3)

Run in the cloud sandbox: backend on `.env.ci-tests` (empty CI database, one company SRT), Next dev
server, headless Chromium with software WebGL (SwiftShader). Users: one admin, one staff user with no
role permissions (so no `sales.reports.view`). The snapshot in Redis is a stored realistic fake for
today's MYT date (30 shops, 8 lit, one stall, 6 warehouse pools, `compare`, `deliveries`); the endpoint
reads Redis only. Navigation was by sidebar click from `/` (agent-browser for the first pass,
Playwright with the same flow for the measured runs; screenshots at deviceScaleFactor 2,
palette-compressed to stay under the 200 KB png cap).

## Screenshots

| File | Shows |
| --- | --- |
| 01-admin-1280-hint.png | Admin 1280x800: the five cards, 3D scene (scoreboard, lit shop tags, red "! 1,749 low", "To deliver: 17", approvals badge), legend, "Tap any building" hint |
| 02b-admin-1280-panel-sales.png | Tap on the scoreboard opens "Today's sales" (hint is gone) |
| 03-admin-1280-panel-shop.png | Tap on a lit shop: "Bought today, rank 1 of 30" |
| 04-admin-1280-panel-low.png | Tap on the red "!": "1,749 products low" |
| 05-admin-1280-panel-deliver.png | Tap on the depot: "17 to deliver" |
| 06-admin-1280-panel-approvals.png | Tap on the approvals office: "Approvals, 2 waiting" |
| 08-admin-1280-wallboard.png | Wallboard on: shops read "Shop #n"/"Dealer", only 3 inv counts, no per-shop RM, total kept |
| 09, 10, 11 (admin-375) | 375x812: top of the page, the cards stacked below the scene, a panel as a bottom sheet |
| 12-staff-1280-no-amounts.png | User without the sales report permission: no RM, anonymous "Dealer" shops, counts present |
| 13-admin-1280-reduced-motion-cards-only.png | prefers-reduced-motion: cards only |
| 14-admin-1280-no-webgl-cards-only.png | WebGL disabled: cards only |

## Measurements

- Hint: visible on first open, gone after a tap (localStorage remembered).
- 375x812: `scrollWidth` 375 = viewport (no horizontal page scroll); cards start at y 822, below the scene
  (bottom 805); panel box inside the viewport.
- Staff user: page text has no "RM", no money-shaped figure, no dealer name, no UUID; the network body has
  none of `amount`, `today_amount`, `ninety_day_amount`, `last_week_amount`, no `name` or `code`, shop keys
  `s1..sN`; counts shown (237 invoices, 64 dealers, 1,749 low, 17 to deliver, 2 waiting).
- Wallboard body (admin): shop keys are only `key, account_label, kind, rank, today_docs`; total amount kept.
- No console errors or page errors on the Town page in any run. The only 4xx in the logs is
  `GET /api/auth/dev-login/users` 404 from the sign-in page, before Town opens (not Town).
- Draw calls per rendered frame: 22 (limit 100), at 1280 and at 375.
- Pixel ratio on a DPR 3 device: canvas buffer / CSS width = 1.5 at both widths.
- Idle: 0 rendered frames and 0 draws in 5 s idle (and 0 in 3 s after a drag), at CPU throttle 6x.
- Drag at CPU throttle 6x (40 pointer moves, software GL, so GPU time is the SwiftShader rasteriser):
  render callback p50 7.0 ms, p95 36.6 ms, max 38.6 ms at 1280; p50 7.8 ms, p95 22.8 ms, max 25 ms at 375.
  Gaps between rendered frames: p50 103 ms (1280) and 51 ms (375). That is above 33 ms here, dominated by the
  software rasteriser plus 6x throttle; first frame costs about 260 ms (shader compile). Not representative
  of a real GPU.
- Polling (visible tab, no throttle): `/town/snapshot` at 0 s (200), 60.0 s (304), 120.1 s (304).
- Hidden tab (visibility override): 0 snapshot requests and 0 rendered frames in 75 s; after showing again the
  next poll came 32 s later (304).
- Chunks: on the dashboard, 69 JS chunks and none contains "WebGLRenderer"; on `/town`, 76 chunks and the
  three.js core, module and TownScene chunks do (positive control). Checked on the dev server, not a
  production build.

## Defects and limits found

1. Shop tags overlap each other and are cut off at the right edge of the scene at 1280 and 375 with 8 lit
   shops (see 01 and 09). Readable names can be lost behind neighbours.
2. At 375 the town draws small in the lower half of the scene and leaves a large empty area on top.
3. Panel links go to existing pages, but in this sandbox database 4 of 5 targets
   (`/finance/billing-documents`, `/scm/reorder`, `/scm/sales-orders`, `/procurement-management/purchase-requests`)
   and also `/sales/sales-and-outstanding` on a client navigation bounce back to `/` for the admin, as
   any navigation to them does here (no module rows enabled in the CI database). The link route is entered
   (`/sales/sales-and-outstanding` seen), the redirect is the app's own gate, so link-follow is not
   proven on a fully provisioned database.
3b. The staff scoreboard panel still says "Same figure as the sales report" with no figure (wording only).
