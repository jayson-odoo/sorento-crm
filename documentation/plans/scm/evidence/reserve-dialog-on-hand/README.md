# RESERVE-DIALOG-ON-HAND browser pass (agent-browser, headless, 1280px)

Sandbox DB `sorento_browse` (a copy of the bootstrapped empty CI schema), seeded by
`harness/seed_browse.py`. All names are invented: admin `browse.admin@example.com`, product
`ZZT-ONHAND-01` "Test basin", pool `BRW` with member `BRW-BB`, SOs `ZZTSO0001` / `ZZTSO0002`.
The seed's numbers are the reported shape: 171 on hand at BRW, an open line of 6 on a
NON-transferable SO at BRW, an open SPO allocation of 4 at BRW. The old dialog figure would
have been 171 - 6 + 4 = 169. Every module was installed for the tenant (a fresh DB has none, so
the sidebar is empty without it). Backend uvicorn :8000 on `.env.browse`, frontend `npm run dev`
:3000. Navigation by sidebar clicks from `/`. No console errors or page errors.

| Step | Screenshot | Result | Observed |
|---|---|---|---|
| Inventory > Stock status, item ZZT-ONHAND-01 | 01-stock-status-1280.png | reference | BRW row: On hand 171, SO qty 0 (non-transferable SO left out), SPO qty 4, Available 175. |
| Procurement > Supply Chain > Order Inquiries > OI-2611-0001, tick the line, options > Request CS to reserve | 02-request-cs-reserve-dialog-1280.png, 03-request-cs-reserve-location-open-1280.png | PASS | Location reads `BRW on hand 171`; the open list offers `BRW on hand 171`. Equals Stock status On hand. Request sent (201). |
| Same line, Reserve column > Edit reserve (the CS reserve form) | 04-cs-reserve-form-location-open-1280.png | PASS | Location option `BRW` with description `on hand 171`. |
| Procurement > Supply Chain > Stock Debt > Save snapshot > open it > Decide > Reserve > From | 05-snapshot-reserve-from-open-1280.png | PASS | From offers `BRW on hand 171` (crew ruling: every reserve picker shows plain on hand). |
