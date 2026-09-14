# Evidence - low stock report

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
