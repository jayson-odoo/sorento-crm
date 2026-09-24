# Round 4 browser evidence (AC-RS-90)

agent-browser, session `oireserve-r4`, :3080 from `/` by sidebar (Procurement -> Supply
Chain -> Order Inquiries), logged in as `tehjayson@gmail.com` (holds both the requester
and reserve permissions on this stack, so one login covers both roles this walk needs).
Live OI: `OI-000020` (`fe55c311-7275-4727-8000-4bb5e7501137`), lines MWCX7605-S-RL /
MWCY7605 / MKT5529SS-DIY, all `ORDER BACK`, qty 3 each - already carrying an OPEN reserve
request #1 from an earlier session, which is what this walk answers.

While driving this walk I found and fixed a real backend bug (see "Bug found and fixed"
below) - the screenshots below are from AFTER that fix, on the live `--reload`d backend.

| AC | what was checked | file | result |
| --- | --- | --- | --- |
| AC-RS-83 | Lines grid State filtered to "Request to reserve": amber `Request to reserve 3` pills, tick + pencil icons, no header badge | `AC-RS-83-overview-1280.png` (plain `On PO/SPO` pill on an unrelated row, no reserve icons) | PASS |
| AC-RS-84 | Tick on MWCX7605-S-RL stages `Reserve 3 @ BRW` chip + Undo, no dialog, nothing posted until commit | (see AC-RS-83-84-85 below) | PASS |
| AC-RS-85 | Pencil on MWCY7605 opens `ReserveLineForm`, Location `SearchableSelect`, Reserved input, Reason field, staged `Reserve 2 @ BRW` chip | `AC-RS-83-84-85-lines-reserved.png` (post-commit state, both chips resolved to green pills) | PASS |
| AC-RS-87 | Header `Reserve (2)` enabled once 2 rows staged; click posts ONE commit; toast `Reserved, Jayson Foundryx notified`; button greys back to disabled `Reserve` | `AC-RS-87-amend-committed-toast.png` | PASS |
| n/a | Grid shows `Reserved 3` / `Reserved 2` green pills with tick, `Amend reserve` + `History` icons, after commit | `AC-RS-83-84-85-lines-reserved.png` | PASS |
| n/a | One outbox row per commit, each naming only the rows THAT call touched, with "N line(s) still to reserve" (AC-RS-80/81) | DB check below | PASS |
| AC-RS-86 | `Amend reserve` on MWCY7605 (already `Reserved 2`): Location renders as locked plain text `BRW` (no select), Reserved prefilled with the net (2); staged `Amend to 1` + Undo; committed via the SAME header CTA, toast fires again, pill becomes `Reserved 1` | `AC-RS-87-amend-committed-toast.png` (post-commit `Reserved 1`); `AC-RS-86-amend-form-375.png` (the form itself, at 375px, on the still-full row) | PASS |
| AC-RS-89 | `History` opens `ReserveLineHistoryDialog`, newest first, `formatDateTime` (no raw ISO): `Unreserved 1 @ BRW - transferred back`, `Reserved 2 @ BRW - BRW only has 2 in stock`, `Requested 3 @ BRW` | `AC-RS-89-history-reserve-then-unreserve.png` | PASS |
| AC-RS-88 | State `SearchableMultiSelect` (7 options in the UAC's own order: To buy, Partly on PO/SPO, On PO/SPO, Done, Cancelled, Request to reserve, Reserved), filters the grid live | `AC-RS-88-state-filter-1280.png` | PASS |
| AC-RS-90 (375px) | Header `Reserve`/`Confirm` buttons and the Lines tab usable at 375px, no clipping; `ReserveLineForm` opens correctly at 375px (Stage/Cancel full width, no overflow) | `AC-RS-90-mobile-375.png`, `AC-RS-86-amend-form-375.png` | PASS |

## Outbox rows (DB, `email_outbox` on `sorento_oireserve_stack`)

Two rows for `Reserved: OI-000020 #1 - SO419851`, one per commit click, each naming only
that click's own rows (AC-RS-81):

```
created_at 02:57  to=jayson@foundryx.my cc=elingkoh@sorento.com.my
  body contains MWCX7605(yes) MWCY7605(yes) MKT5529(no) "1 line still to reserve."(yes)
created_at 03:07  to=jayson@foundryx.my cc=elingkoh@sorento.com.my
  body contains MWCX7605(no) MWCY7605(yes) MKT5529(no) "1 line still to reserve."(yes)
```

## Bug found and fixed during this walk

`_HAS_OPEN_RESERVE_REQUEST` and the new `_OPEN_REQUEST_QTY`
(`order_inquiry_worklist_service.py`) tested only "does the row's PARENT request still
carry state `requested`" - not "is THIS row's own answer still unset". Round 1-3's
per-row route answered every row of a request in lockstep, so the parent's own state was
an accurate proxy; round 4's `commit_request` can now answer PART of a request in one
click while the parent stays `requested` until its last row lands, which the live walk
surfaced immediately: after committing MWCX7605-S-RL (answered) while MKT5529SS-DIY (same
request, still open) kept the parent at `requested`, the grid kept showing
`Request to reserve 3` / the tick+pencil icons on the ALREADY-answered row instead of
`Reserved 3` / amend+history - confirmed via `console.log` of the raw worklist API
response (`reserve_state: "requested"` despite `order_inquiry_reserve_request_rows.
qty_reserved = 3` in the database) and via a direct SQL replay of the subquery. Fixed by
adding `OrderInquiryReserveRequestRow.qty_reserved.is_(None)` to both subqueries' own
`WHERE`. Backend suite re-run green after the fix (111 passed:
`test_order_inquiry_reserve.py` + `_round2.py` + `_commit.py` + `test_order_inquiry_
worklist.py`); confirmed live via reload (screenshots above are all post-fix).
