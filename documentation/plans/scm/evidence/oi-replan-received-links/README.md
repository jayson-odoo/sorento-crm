# Browser evidence run - oi-replan-received-links

Branch `worktree-agent-a094ed68b05447f09`, HEAD `234442b2d`, run 17 Sep 2026 (session tz
shows 16 Sep 2026 UTC-ish timestamps below; local server clock reads "17/09/2026" in-app).
Tool: `agent-browser@0.27.0`, session `oirl-verify`. Stack used: frontend `:3000` (`next dev`,
already running), backend `:8000` (already running), database
`sorento_ai_automation_0915_1900` (15 Sep prod copy) for everything done before the collision
described below.

## Environment collision that cut the run short

Mid-session (after AC-RL-30's Confirm action, while navigating to Order Inquiries) my logged-in
session started failing with `401 {"code":"session_invalid"}`, and a fresh login returned
`404 User not found. Please register first.` from `POST /api/v1/auth/login`.

Root cause, confirmed by inspecting the live worktree: `sorento_crm_backend/.env` now points
`DATABASE_URL`/`DIRECT_URL` at `sorento_oirl_ci` (a blank/CI test database), and an untracked
`sorento_crm_backend/.env.owner-live-backup` sits alongside it holding the ORIGINAL
`DATABASE_URL=...sorento_ai_automation_0915_1900`. `ps aux` showed a `uvicorn --reload`
multiprocessing worker (pid 5148) only ~51s old at the time I checked, i.e. the coder's
concurrent pytest work in this same worktree (git status shows
`sorento_crm_backend/tests/test_ingest_documents_v5_so_po_links.py` modified - the AC-RL-32
ingest test) swapped `.env` to run its own suite against the CI database and the `--reload`
watcher picked it up, restarting the shared backend process mid-verification. This is a
same-worktree tester/coder resource collision, not a product defect. No pytest process was
still running when I checked afterward, but `.env` had not yet been restored, so I left it
alone rather than flip it myself (not this run's file to own, and the coder may still need it).

**Everything from AC-RL-02 onward that needed a live browser session is therefore NOT
exercised in this run.** Recommend: coder/captain restores `.env` from `.env.owner-live-backup`
once their test round is done, then a short follow-up browser pass covers the remaining items
below.

## AC-RL-01 - What changed dialog shows years - PASS

Fulfilment Planning -> searched SO314593 -> opened the plan (batch `525655a7-...`) -> List view
-> clicked "What changed" on line 1 (B2154-NL)'s Date cell.

Dialog read exactly:
```
Qty 182 -> 220
Date 1 Jun 2026 -> 1 Mar 2027
Decision Not stated -> Buy 220
```
Both dates carry the year, "Jun"/"Mar" hand-rolled short form. Screenshot:
`AC-RL-01-what-changed-date.png`.

## AC-RL-06 - board list inquiry cell shows `received`/`used` before confirming - NOT
VISUALLY EXERCISABLE on this line/dataset, code + data contract independently verified

Traced the FE code path: `FulfilmentBoardListView.tsx`'s "Decided" column only prints the
inquiry word (`received`/`used`) via `contributionInquiryDecision()`, which requires
`contribution.covered === true && contribution.decision == null` (a line the ladder never had
to touch because an existing OI row already answers it). I fetched the live board JSON
directly (`GET /api/v1/project-sales/fulfilment-planning/board?orders=SO314593&granularity=week`,
same bearer token the browser was using) and confirmed `covered` is `false` for every one of
the 16 contributions on this board, including B2154-NL's line 1 - consistent with the plan's
own journey text ("the board's ladder ... proposes Buy 220", i.e. the engine actively computed
a fresh proposal because the SO change from 182 to 220 uncovers the old OI row). So the
`received`/`used` word genuinely cannot render for this specific line under this specific
journey; the AC's mechanism is real and reachable in general, just not on a line the ladder is
actively deciding.

What I DID confirm from that same raw JSON is the AC-RL-07 backend contract, which the AC-RL-06
word depends on:
```json
"order_inquiry": {
    "inquiry_no": "OI-000477",
    "state": "partly_linked",
    "documents": [{"document": "SPO-2026/01-0143", "kind": "spo", "received": true}],
    "redirected": false
}
```
present and correct on B2154-NL's contribution. Screenshot of the board list pre-confirm (no
word visible, as expected given `covered: false`): `AC-RL-06-board-list-pre-confirm.png`.
Flagging for the reviewer: worth double-checking with the coder whether AC-RL-06 is meant to be
demonstrable on the exact line the UAC names, or whether the UAC's journey and the `covered`
gate are simply describing two different moments (this run could not settle it visually).

## AC-RL-30 - Confirm all, redirected + new row - PASS at the UI action and DB level;
Order Inquiries page NOT screenshotted (collision)

Clicked "Confirm (10)" on the SO314593 plan, confirmed the "Confirm 10 lines across 1 order?"
dialog. Result banner: "SO314593: confirmed as revision 1 (5 purchase rows handed over)".
Screenshot: `AC-RL-30-confirm-success.png`. Console showed only a pre-existing
`AlertDialogContent` missing-description a11y warning (Radix pattern used elsewhere in the app,
not new to this lane) - no hard errors.

Confirmed via the batch table that this landed in the right database:
```
select id, applied_at, applied_by, order_count, line_count
from projects.planning_change_batches where id = '525655a7-d4cd-4c6f-8f58-5639ed1e1506';
-- applied_at 2026-09-16 17:16:00, order_count 1, line_count 14
```

I could not reach Order Inquiries in the browser afterward (session died - see collision above),
so I read the two resulting rows directly instead, as a substitute for the screenshot the AC
asks for:
```
inquiry_no | item_code | qty | state         | redirected_to_pool | delivery_date | note
OI-000477  | B2154-NL  | 182 | partly_linked | t                   | 2027-03-01    | "...SPO-2026/01-0143 received in full, goods are BRW-IR stock, released at revision 1"
OI-000477  | B2154-NL  | 220 | raised        | f                   | 2027-03-01    | (empty)
```
and the links table shows the 182 row keeps its SPO-2026/01-0143 link (158 qty, `auto=true`)
and the 220 row has zero links. This matches AC-RL-10/11/30's spec exactly (redirected row
unchanged qty/date/links plus the note suffix, fresh ORDER row with no links). What it does
NOT confirm is the FE rendering (the `received`/`used`/grey pills, the Qty lightbox, the Buy
card total) - that needs the browser pass once the DB is restored.

## AC-RL-02 / AC-RL-24 (SO314594 reallocate/unlink chips) - NOT EXERCISED (collision)

Blocked before I reached this SO. Not attempted at the DB level either, since the
`suggestion.kind` value is computed at read time by the service layer (lead-time comparison +
candidate query), not stored, so there is nothing to read straight from Postgres for this one.

## AC-RL-31 (re-run Auto link all, both rows keep their link count) - NOT EXERCISED (collision)

Also skipped the OI sheet re-upload regardless, per the brief's instruction, since I did not
have the 15 Sep OI sheet file in hand.

## AC-RL-32 (ESB ingest moving a PO's `from_so_line_ref`) - NOT EXERCISED live; covered by
the coder's own test file

Did not attempt the raw ingest POST - the collision above is literally the coder mid-run on
`tests/test_ingest_documents_v5_so_po_links.py`, which is the test file this AC maps to. Per
the brief's own fallback instruction, marking this covered by that pytest file rather than by a
live ingest call in this run.

## AC-RL-05 (375px viewport on Order Inquiries) - NOT EXERCISED (collision)

Never reached the Order Inquiries page in this session.

## Console / network summary

- No unexpected console errors on Fulfilment Planning before the collision.
- One pre-existing Radix `AlertDialogContent` accessibility warning (missing description) on
  the Confirm dialog - not introduced by this lane, not blocking.
- One unrelated `500` on `GET /api/v1/scm/sales-orders/{id}` observed when a board row's SO
  link was clicked (navigates to the SO detail page) - not something this UAC touches; noting
  it so it is not lost, but out of scope for this lane's verification.
- After the collision: `401 session_invalid` then `404 User not found` on every subsequent
  request, tracked back to the `.env` DB swap above, not a frontend or auth-boundary defect.

## What still needs a follow-up pass

Once `.env` is restored to `sorento_ai_automation_0915_1900` (from
`sorento_crm_backend/.env.owner-live-backup`) and the backend reloads:
- Screenshot Order Inquiries for SO314593 (AC-RL-30's FE half: greyed row, `received`/`used`
  pills, Qty lightbox, Buy card total).
- SO314594 CB2805A-DIY / CB2807-DIY chips (AC-RL-02/24).
- Auto link all re-run (AC-RL-31).
- 375px viewport pass (AC-RL-05).
- Revisit AC-RL-06 with the coder to confirm whether the UAC's own journey line is expected to
  show the word, or whether it is deliberately never reachable on an actively-decided line.
