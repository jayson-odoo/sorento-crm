# S5 evidence: delivery schedule review screen

Component-level, 26 Sep 2026. This cloud lane has no Postgres rows, no backend `.env` and no
NextAuth login, so the real `DeliveryScheduleReviewClient` was rendered from its own `?demo=`
fixture on a scratch route (not committed) under `next dev`, in the preinstalled Chromium. No
console errors, no failed requests. The HQ/26/01/121 v2 pass on a local stack (S5-7) is still
owed. In demo mode there is no server to record a dismissal, so "Dismiss with a reason" is not in
these popovers; it is covered by `DeliveryScheduleFlagCell.test.tsx` and
`DeliveryScheduleReviewClient.test.tsx`.

Horizontal scroll, measured: page scrollWidth minus clientWidth is 0 at 1280 and at 375; the
matrix scrolls inside its own container (1520px of overflow at 1280).

| File | Shows |
| --- | --- |
| `s5-1-schedule-need-attention-1280.png` | Header, two tabs, toolbar, Need attention (2) by default |
| `s5-2-flag-popover-1280.png` | A Flag pill opened: one line per finding, the picker, Fix the quantities |
| `s5-3-schedule-all-rows-1280.png` | All rows (6), Agrees pills, per-date totals over every row |
| `s5-4-history-sheet-1280.png` | History: changes since the previous version, re-dating, notes |
| `s5-5-documents-1280.png` | Documents with no file: the R13 not-available state |
| `s5-6-confirmed-all-rows-1280.png` | A confirmed version: opens on All rows, no Confirm button |
| `s5-7-schedule-need-attention-375.png` | The phone cards, one Flag pill each |
| `s5-8-flag-popover-375.png` | The same popover at 375 |
| `s5-9-documents-375.png` | Documents at 375 |

## Review fixes (reviewer pass on #1265, 26 Sep)

Same method: the real client off `?demo=data` on an uncommitted scratch route under `next dev`,
in the preinstalled Chromium, driven by a throwaway script. No console errors, no failed
requests; page horizontal overflow 0 at 1280 and at 375.

| File | Shows | Measured |
| --- | --- | --- |
| `s5-fix-b1-row-kept-mid-edit-1280.png` | B1: "8" typed into "Level 2 & 7, SRTFV1001" in the default Need attention view | The row stays, focus stays in that input (value "8"), both rows still listed; the count reads Need attention (1) |
| `s5-fix-b2-by-date-scrolled-1280.png` | B2 at 1280: By date scrolled 600px | Product and Flag both still pinned (left 1 and 241) |
| `s5-fix-b2-by-date-375.png` | B2 at 375: By date at rest | Scroller 341px wide, one pinned column (Product, 240px) |
| `s5-fix-b2-by-date-scrolled-375.png` | B2 at 375: By date scrolled | The first date column's quantities (135, total 410) in view beside the pinned product |
| `s5-fix-need-attention-375.png` | By area at 375 after the fixes | Phone cards unchanged |
