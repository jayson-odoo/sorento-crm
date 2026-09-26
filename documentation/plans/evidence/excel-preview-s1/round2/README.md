# Round 2 evidence: owner hand test 26 Sep (W1 to W6)

Recorded 26 Sep 2026 with agent-browser 0.27.0 (headless Chromium) against a local stack on
this lane's branch at `71df03d2`: FastAPI on :8000 and `npm run dev` on :3000, with Postgres 16
built by `scripts.bootstrap_env`. The run used no worker, because no download was tested.

**Demo data:** one completed reorder run with 42 products across 15 suppliers (one is blank,
one is "AFFINARE BUILDING MATERIALS SDN BHD") and 5 categories. The default split gives 68
sheets. The user was a `purchasing` role user. Navigation went by sidebar clicks from `/`.

| # | Screenshot | What it shows |
| --- | --- | --- |
| 01 | `01-sidebar-no-low-stock-1280.png` | Procurement > Supply Chain has no "Low stock report" item (W5). |
| 02 | `02-back-button-1280.png` | Reorder Planning, a plan, Actions > Low stock report Excel opened `/scm/low-stock-report/<run>`. The header shows "Back to Reorder planning" top right (W6). Clicking it landed on `/scm/reorder/<same run>`. |
| 03 | `03-supplier-filter-plain-1280.png` | The supplier options are plain names, with no "N low of M" (W1). |
| 04 | `04-sheet-search-1280.png` | There is no "Go to sheet" dropdown (W2). The strip's "..." opened "Search sheets"; "nusantara" narrowed 68 sheets to 6 (W3). |
| 05 | `05-sheet-jumped-1280.png` | Picking "Nusantara Cement Supp (3)" opened that tab and scrolled the strip to it (W3). |
| 06 | `06-product-code-search-1280.png` | "Search product code": `P026` gave 1 row, and part of a description matched too (W4). |
| 07 | `07-page-375.png` | At 375px, scrollWidth equals clientWidth (375). The "..." and the search box stay usable. |

**Bare path:** `/scm/low-stock-report` redirected to `/scm/reorder` (W5).

**Console:** the only error is the existing `Demo1Layout` missing-key warning.

**Breadcrumb:** these screenshots predate the fix. They show the trail falling back to
"Dashboards > Supply Chain > Dashboard", because no sidebar item names the page any more. The
page now passes its own trail: Procurement > Supply Chain > Reorder Planning > Low stock report.
`LowStockReportView.test.tsx` covers it: "W5: the trail runs through Reorder Planning, since no
sidebar item names the page".
