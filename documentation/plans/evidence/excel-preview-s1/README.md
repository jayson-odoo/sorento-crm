# S1 evidence: low stock report page (PLAN-excel-preview-26sep)

Recorded 26 Sep 2026 with agent-browser 0.27.0 (headless Chromium) against a local stack on
this lane's branch: FastAPI on :8000, the RQ worker, `npm run dev` on :3000, Postgres 16 built
by `scripts.bootstrap_env`. Storage for the run was a local folder (a scratch launcher swapped
the S3/R2 backend for the API and the worker; not committed), because the cloud environment has
no bucket credentials. Demo data: one completed reorder run, 420 products, 8 suppliers plus a
blank one, 8 categories.

Navigation started at `/` and went by sidebar clicks.

| # | Screenshot | What it shows |
| --- | --- | --- |
| 01 | `01-page-1280-default-split.png` | Procurement > Supply Chain > Low stock report opens the newest run. Split pills with "Supplier and category" selected, both filters on "All", "420 rows, 144 sheets", sheet tabs with a dot on each "- Low" sheet, "Go to sheet" (more than 12 sheets), frozen header, numbers right-aligned, the grid scrolling sideways in its own container. Page scrollWidth 1280 = clientWidth. |
| 02 | `02-supplier-filter-open-1280.png` | The Suppliers multi-select: every supplier of the whole run, "No supplier" included, each with "N low of M". |
| 03 | `03-supplier-split-two-suppliers-1280.png` | Split "Supplier" + Hansgrohe MY and Kohler Asia: "85 rows, 4 sheets". The request carried `split=supplier&supplier=Hansgrohe%20MY&supplier=Kohler%20Asia`. |
| 04 | `04-preparing-1280.png` | Download pressed with the worker paused: the button reads "Preparing..." (disabled), the My Downloads badge shows the row in flight. With the worker restarted the file saved on its own and the button returned to "Download". |
| 05 | `05-my-downloads-1280.png` | Both low stock files are Ready in My Downloads. |
| 06 | `06-page-375-default.png` | 375px: page scrollWidth 375 = clientWidth; toolbar wraps by group; the split strip scrolls inside the card; the grid scrolls sideways (341px wide, 1724px of columns). |
| 07 | `07-page-375-split-none.png` | 375px, split "None" reached by scrolling the strip: "Low stock" and "All". |
| 08 | `08-reorder-actions-menu-1280.png` | Reorder Planning, the run's Actions menu, "Low stock report Excel". |
| 09 | `09-from-reorder-planning-run-page-1280.png` | That item opened `/scm/low-stock-report/<run>`; no dialog. |
| 10 | `10-email-link-after-sign-in-1280.png` | The email's link opened signed out: sign-in page with `callbackUrl=/scm/low-stock-report/<run>`, then back on that run's page after signing in. |

## The file is the view

The workbook the page saved (split Supplier, Hansgrohe MY + Kohler Asia) was read back with
openpyxl and compared with `GET /low-stock-view` for the same request:

```
file sheets: ['Hansgrohe MY - Low', 'Hansgrohe MY', 'Kohler Asia - Low', 'Kohler Asia']
view sheets: ['Hansgrohe MY - Low', 'Hansgrohe MY', 'Kohler Asia - Low', 'Kohler Asia']
  Hansgrohe MY - Low: file 23 rows, view 23 rows, identical=True
  Hansgrohe MY: file 42 rows, view 42 rows, identical=True
  Kohler Asia - Low: file 16 rows, view 16 rows, identical=True
  Kohler Asia: file 43 rows, view 43 rows, identical=True
ALL IDENTICAL: True
```

`tests/scm/test_low_stock_view.py::test_view_and_workbook_agree` pins the same property for all
four splits and two filtered cases.

## Export timings (owner ruling 26 Sep, Q8)

`tests/scm/bench_low_stock_export.py` (not collected by the suite; run by path with `-s`):
5,000 frozen rows, 60 suppliers x 25 categories, 2,790 of them low, tables analysed. Best of
three, same machine, same data.

| Case | Before (main 46711c61) | After (this lane) |
| --- | --- | --- |
| Read the frozen run (`_split`) | 0.53 s | 0.50 s |
| Export, split None (2 sheets) | 5.49 s | 2.10 s |
| Export, split Supplier and category (600 sheets) | 7.49 s | 3.20 s |
| View route payload build, split None | n/a | 0.68 s, 988 KB JSON |
| View route payload build, Supplier and category | n/a | 0.64 s, 1.03 MB JSON |

The write went from about 5.0 s to 1.6 s (None) and from 6.9 s to 2.6 s (600 sheets):
openpyxl write-only mode with one shared style array per cell kind, instead of appending
every row and then restyling every cell. What is left is openpyxl's own XML serialisation.
Installing `lxml` (openpyxl uses it when present) measured a further 20% on the write alone
(1.47 s to 1.18 s on the same rows); not taken here, because it changes the serialiser for
every export in the app, and 20% did not pay for that.

In the browser run the worker built the 85-row, 4-sheet file in 1.0 s.

## Not covered here

- A real email: the trigger is covered end to end through the engine in
  `tests/scm/test_low_stock_report_ready_trigger.py` (an automation on the trigger queues its
  template, rendered with the run's link, to its own recipient). The live automation row that
  sends the email today is data in the production database; an admin points it at the "Low
  stock report ready" trigger and puts `{{ report.link }}` in its template.
- A known console error in the app shell (`Demo1Layout`, missing list key) shows as the Next
  dev "1 Issue" badge on every page; it is not from this lane.
