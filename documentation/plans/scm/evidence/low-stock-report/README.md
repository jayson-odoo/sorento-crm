# Evidence - low stock report

## S1 (AC-17) - an unscoped run before and after the second admission leg

Local 0907 prod copy (`sorento_ai_automation_0907`), 14 Sep 2026, engine run in-process
(`create_run(db, None, "warehouse", enqueue=False)` then `run_reorder`), not through the worker.
Global `scm.reorder_policy.dead_stock_days` = 180.

| Run | Recommendations | Products planned | Buys | needs_level | Wall |
| --- | --- | --- | --- | --- | --- |
| Before - 10/09 02:10, the newest completed unscoped run on the committed-demand leg alone | 950 | 950 | 374 | 1 | 4.1 s |
| Before - 10/09 01:55 | 950 | 950 | 374 | 1 | 4.1 s |
| Before - 10/09 01:54 | 950 | 950 | 374 | 1 | 4.5 s |
| **After - 14/09 09:01, both legs** | **2,017** | **2,017** | **1,151** | 1 | **8.5 s** |

What the second leg admits on its own, measured with the same predicate the engine now runs:

- 2,697 products are below their resolved level (a person's product-wide `scm.reorder_level`
  row with `source in (manual, accepted_suggestion)`, else `products.reorder_level`, 0 is not a
  level) against site-pool on hand at `counts_as_available` warehouses.
- 1,433 of those still moved inside 180 days - the dead guard keeps the other 1,264 out.
- Union with the 950 the committed-demand leg already admitted = the 2,017 planned above, so
  366 products satisfy both legs.

Against the plan's estimate: products landed at 2,017 rather than the forecast ~1,600 (the
estimate came off the "7,778 below level, 582 in the last run" figures rather than from running
the predicate), and wall time is 8.5 s against a 15 s ceiling - roughly double the 4.1 s
baseline, for roughly double the products, which is the same ~4 ms a product the plan measured.
777 new buy rows reach the buyer; that is the report's whole point (CB100-BL-DIY's shape).

## S4 (Phase 1) - agent-browser run, 14 Sep 2026

Lane dev server `npm run dev -- -p 3084` from the lane worktree (:3080/:3081/:3082 were held by
other lanes), `FASTAPI_INTERNAL_URL=http://localhost:8000` (the primary backend, on the 0907 prod
copy). agent-browser 0.27.0, isolated session `lowstock-3084`.

Navigation, sidebar clicks only from `/`:
Dashboards -> Procurement -> Supply Chain -> Reorder Planning -> plan `10/09/2026 10:10`
(`/scm/reorder/00788044-...`, 377 lines).

| Step | Read |
| --- | --- |
| Actions menu at 1280x900 | `Order sheet PDF`, `Order sheet Excel`, `Low stock report (Excel)`, `Plan exceptions`, `PO worklist`, `Reset planning` - the new item third, directly under Order sheet Excel (AC-1). Screenshot `s4-actions-1280.png`. |
| Click `Low stock report (Excel)` | `POST /api/v1/scm/order-summary/export`, body `{"run_id":"00788044-...","format":"low_stock_xlsx"}` -> `422` (AC-2's request shape). The backend has no such format until S3, so the toast reads the extracted server message, `format must be pdf or xlsx.` - `extractApiError` is doing its job; nothing is hand-rolled. |
| Actions menu at 375x812 | All six items render, none clipped, `Low stock report (Excel)` fully readable in a 216px menu (AC-5). Screenshot `s4-actions-375.png`. |
| Plans list at 1280 | Unchanged: `daily` and `superseded` badges render in the Plan column at its existing `size: 190`. No `via chat` row exists yet - `requested_via` is emitted by the backend in S5, and the FE never infers it (AC-4 is covered by `ReorderRunsGrid.test.tsx` until then). |
| Settings > Chatbot Media | `Low stock report chat wait (seconds)` sits in the Pacing card beside `Synchronous wait seconds`, seeded 40 from the service fallback (the column lands in S5); typing `120` refuses inline with "Enter a whole number between 5 and 90." and disables Save (AC-7). Nothing was saved. |

Console: one error, `Each child in a list should have a unique "key" prop` in `Demo1Layout` -
present on the home page before any of this lane's code loads, unrelated.

Not exercised in Phase 1, by design: the workbook itself, the My Downloads row label
(`low_stock_xlsx` rows only exist once S3 writes them), and the `via chat` badge against real data.

## Phase 3 - browser verification (INCOMPLETE, needs re-run / attestation)

**This run was NOT completed or attested by the tester in-session.** The session limit cut the
work short before a browser pass could be driven and written up. The artifacts below are
committed as-is so nothing is lost, but no acceptance criterion should be treated as
browser-verified on their strength alone - the captain should re-run the pass (or an attesting
agent should confirm each shot against its AC) before the DoD gate.

Artifacts present in this directory (inventory only - the tester cannot vouch for what drove
them):

| File | What the filename indicates it captures |
| --- | --- |
| `p3-01-plans-list-1280.png` | Reorder Planning list at 1280 |
| `p3-02-actions-menu-1280.png` | plan Actions menu at 1280 (the three export items) |
| `p3-03-toast-1280.png` | the "preparing" toast after clicking Low stock report |
| `p3-04-my-downloads-1280.png` | My Downloads drawer row for the report |
| `p3-05-plans-list-after-run-1280.png` | plans list after a chat-created run (the `via chat` badge) |
| `p3-06-chatbot-media-wait-1280.png` | System Settings wait field beside the media wait |
| `p3-07-wait-reject-4-1280.png` | the wait field refusing 4 (below the 5..90 bound) |
| `p3-08-wait-60-after-reload-1280.png` | the wait value persisting at 60 after a reload |
| `p3-09-settings-wait-375.png` | the wait field at 375 |
| `p3-10-plans-list-375.png` | plans list at 375 |
| `p3-11-actions-menu-375.png` | Actions menu at 375 (no clipping) |
| `p3-12-toast-375.png` | the toast at 375 |
| `p3-13-my-downloads-375.png` | My Downloads drawer at 375 |
| `low-stock-14092026.xlsx` | a workbook produced during the run (two sheets, container in the incoming cell) |

Which ACs a completed pass must still land, end to end in a real browser: AC-1 to AC-5 and AC-7
(plan-view menu item, download label, `via chat` badge, 375/1280 layout, settings wait field),
the S3 workbook opened and eyeballed (two sheets, sixteen columns, container line in BRW
incoming qty), and the S5/S6/S7 chat path (grant the key, ask "low stock report", receive the
xlsx or the pending line). None of these is attested here.
