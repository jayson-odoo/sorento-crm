# POINT-RATIO-EDIT browser pass (cloud sandbox, 8 Nov 2026)

Sandbox stack: throwaway DB `sorento_browse` (copy of the freshly seeded CI DB, all modules enabled,
one invented superadmin `browse.admin@example.com`), backend uvicorn :8000, frontend `npm run dev`
:3000. Reached by sidebar: `/` > Sales > Targets > Dealers tab > Actions > Point ratio.

| Shot | Width | Result |
| --- | --- | --- |
| 01-rows-with-actions | 1280 | PASS. Each row has Edit and Delete icon buttons (labelled "Edit/Delete ratio from dd/mm/yyyy"). |
| 02-row-in-edit | 1280 | PASS. Pencil swaps the row's date and value for inputs in place, Save / Cancel. |
| 03-edit-onto-existing-date-refused | 1280 | PASS. Moving 08/11/2026 onto 01/01/2026: toast "A ratio from 01/01/2026 already exists. Edit that one instead."; row stays open. |
| 04-edit-saved | 1280 | PASS. 01/12/2026 at 1.35 saved; DB row moved; audit_logs UPDATE row written. |
| 05-delete-countdown | 1280 | PASS. Delete: no dialog, row dims, "Deleting in 8s" + Cancel on a full-width line. |
| 06-deleted-older-ratio-remains | 1280 | PASS. Server committed after the window; only 01/01/2026 1.2 left; audit_logs DELETE row written. |
| 08-row-in-edit | 375 | PASS. Edit row wraps (date, value, then Save/Cancel), nothing clipped. |
| 09-row-calendar | 375 | PASS. Calendar portals out of the dialog, not clipped. Note: it opens on today's month, not the value's month (shared DatePicker behaviour, not this lane). |
| 10-delete-countdown | 375 | PASS. Countdown full width, Cancel on screen; Cancel pressed, row kept (DB unchanged). |

Found and fixed during the pass: at 375 the edit row clipped the date ("01/10/2") and the inline
countdown pushed Cancel off screen. Both now take a full-width line.
