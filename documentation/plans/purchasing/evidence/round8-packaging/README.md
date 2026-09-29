# Round 8 browser evidence: cost per packaging method (#1288, PR #1305)

agent-browser 0.27.0, headless Chromium (`/opt/pw-browsers/chromium-1194`), session `r8`.
Stack: backend on :8000 against a private database `sorento_browse` (built by
`scripts.bootstrap_env`, stamped at `cpc4_cost_packaging_method`), frontend `npm run dev` on
:3000. The `commercial_plus` module bundle was installed so the Procurement sidebar renders.

Seed (direct SQLAlchemy insert): superadmin `round8.admin@sorentocrm.dev`; supplier TAIYANG
(XIAMEN TAIYANG TECHNOLOGY); products `CB2500SS-BL` (linked, CNY 9.00), `CB2500SS-BL-DIY` (not
linked) and `CB2500SS-GY` (linked, CNY 8.00). Upload file `taiyang-2500-series-20260928.xlsx`,
sheet `25系列`, built with `simple_price_list_workbook`:

| Row | Code cell | Cost |
| --- | --- | --- |
| 7 | CB2500SS-BL（彩盒） | 9.50 |
| 8 | CB2500SS-BL-DIY（OPP） | 9.90 |
| 9 | CB2500SS-BL-DIY（吊卡） | 9.40 |
| 10 | CB2500SS-BL | 9.20 |
| 11 | CB2500SS-GY | 8.50 |
| 12 | CB2500SS-GY | 8.60 |

Every screen was reached by sidebar clicks from `/` (Procurement > Cost Price Uploads,
Procurement > Suppliers > TAIYANG > Costs).

| Shot | What it shows |
| --- | --- |
| `01-upload-dialog-1280.png` | Upload cost list dialog, supplier and currency pre-filled from the file. |
| `02-lines-packaging-column-1280.png` | Cost changed card: `CB2500SS-BL` 彩盒 (cost now none, new 9.50), `CB2500SS-BL` standard (9.00 to 9.20), `CB2500SS-GY` standard (8.00 to 8.50, the same-packaging duplicate row 12 inline as "· 8.60"). Packaging column sits beside Supplier code. Header widths 85/145/80/70/150/100/100/70; table 950px inside its 950px wrapper. |
| `03-new-link-card-two-packagings-1280.png` | New for this supplier card: `CB2500SS-BL-DIY` OPP 9.90 and 吊卡 9.40, two lines. |
| `04-packaging-filter-standard-1280.png` | Packaging filter (system `SearchableMultiSelect`, options 彩盒, OPP, 吊卡, standard) on `standard`: two rows; the cards read Cost changed 2, New for this supplier 0. |
| `05-sort-by-packaging-1280.png` | Packaging header sort: standard, standard, 彩盒. |
| `06-cards-packaging-375.png` | 375: the cards show the packaging beside the code (`CB2500SS-BL-DIY OPP`, `CB2500SS-BL-DIY 吊卡`); page scrollWidth 360, no horizontal scroll. |
| `07-applied-1280.png` | "Apply 5 changes" applied. Database after: five cost rows (BL standard 9.20, BL 彩盒 9.50, DIY OPP 9.90, DIY 吊卡 9.40, GY standard 8.50). Link prices: BL 9.20 (standard line), GY 8.50, DIY empty (a new link with two packagings and no standard line keeps no price, AC-CL-04 as amended). |
| `08-supplier-costs-packaging-1280.png` | Supplier Costs tab: one row per product and packaging, Product and Packaging columns first, each row's Source names CPC-0001 and its file row. |
| `09-supplier-costs-sort-cost-1280.png` | Sorted by Cost: 8.50, 9.20, 9.40, 9.50, 9.90. |
| `10-supplier-costs-filter-opp-diaoka-1280.png` | Packaging filter on OPP and 吊卡: the two `CB2500SS-BL-DIY` rows. |
| `11-supplier-costs-375.png` | Costs tab at 375: the grid scrolls inside its card. |

Console: no errors. Every /api/v1 call from the pages returned 2xx (the only 4xx in the backend
log are the setup script's own module-install probes).

Pre-existing, not from this round: the supplier record page at 375 is 383px wide on every tab
(Details included). The overflow is the record header's button row (record navigation and the
options menu), which this round does not touch.
