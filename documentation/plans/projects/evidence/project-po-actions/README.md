# PROJECT-PO-ACTIONS browser pass (agent-browser 0.27.0, headless)

Cloud sandbox stack: backend uvicorn :8000 on the `scripts/cloud-env-setup.sh` database (bootstrap seed plus
one invented project, TAMAN DELTA FASA 4, an admin and a view-only user), frontend `npm run dev` :3000.
Navigated by sidebar clicks from `/`: Project Sales > Projects > Grid view > PPF2610001 > Orders tab.
Console and page errors: none, in both sessions.

| Check | Screenshot | Result | Notes |
| --- | --- | --- | --- |
| 1280: toolbar order | po-row-1280.png | PASS | Search POs, Columns on the left; Actions (outline) then Upload a PO document (primary, last) at the right end. No Record a PO button. |
| 1280: same grammar as the Quotations tab | q-1280.png | PASS | Same header height and clusters as the sibling tab. |
| 1280: Actions menu | po-menu-1280.png | PASS | One item, "Record a PO". |
| 1280: Record a PO opens the same dialog | po-dialog-1280.png | PASS | "Record a purchase order"; saving PO-BROWSE-01 added the row. |
| 1280: Upload a PO document | (not kept) | PASS | Opens "Upload a customer PO", unchanged. |
| 1280: search | (not kept) | PASS | "browse" keeps PO-BROWSE-01; "zzz" shows "Nothing matches that search". |
| 375: toolbar | po-375.png | PASS | Search, Columns, then Actions and Upload right-aligned on their own row. scrollWidth 360 within the 375 viewport, nothing clipped. |
| 375: Actions menu and dialog | po-menu-375.png | PASS | Menu in view; Record a PO opens the same dialog. |
| View-only user | po-viewer-1280.png | PASS | Search and Columns only; no Actions, no Upload a PO document. |
