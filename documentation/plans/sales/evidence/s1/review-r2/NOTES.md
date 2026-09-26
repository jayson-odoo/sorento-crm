# S1 review round 2 evidence (S3)

Local stack on the round 2 head: backend and Next dev (Turbopack, HMR), an empty
`scripts.bootstrap_env` database with seeded Sorento sales orders for 2024 to 2026, a
superadmin login, every catalog module switched on for the tenant (the owner's App Store step,
since S1 no longer switches `sales` on). Reached through the sidebar from `/`:
Sales > Yearly comparison, at 1280 and at 375.

- `1280-top.png`, `375-top.png`, `375-table.png`: the page, the DEALER block, VARIANCE in
  brackets, the chart, and the table scrolling inside its card at 375 (the page is 360px wide
  in a 375px viewport, no sideways scroll).
- `1280-project-variance.png`, `375-project.png`: the PROJECT TEAM block after B1. March 2026
  sold nothing and March 2025 sold 55,000, so MAR is (55,000); September 2026 sold nothing
  before the as-at date, so SEP is (18,000); the total is (16,000), which is 87,000 this year
  to date minus 103,000 over the same months last year. Before B1 the same data read (4,000)
  plus 61,000, a total of 57,000.
- `1280-dev-overlay.png`: the "1 Issue" badge opened. It is a React console error, "Each child
  in a list should have a unique "key" prop. Check the render method of `Demo1Layout`".
- `1280-home-same-badge.png`, `1280-home-dev-overlay.png`: the same issue on a fresh load of the
  Dashboards page, which loads none of S1's frontend files. It also stays with main's
  `menu.config.tsx` and `route-module-map.ts` swapped in (the only layout-level files S1
  touches). So it predates S1 and is not fixed here.
