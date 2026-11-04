# PLAN: OI-RESERVE-USED-ROW (reserve request on a used OI row; snapshot drill "Now" too long)

Status: Diagnose (Step 1, no code yet; waiting on the owner's 4 answers). Track: small fix
expected (no migration, no auth change; FE + BE guard + one repair script), confirmed after answers.

Lane: OI-RESERVE-USED-ROW. Prod case: OI-2609-0257 / SO396347 / SRTSA830-PJ. The request to reserve 33
was stored on the used 55 row (31/12/2026) instead of the live 33 row (04/05/2027) on the same SO line.
Code read at `main` 404bda39.

Mock: `oi-reserve-used-row-04nov-mockup.html` beside this file.

## 1. What "used" means in code

- "used" is the column `order_inquiry_rows.redirected_to_pool` (`sorento_crm_backend/app/models/project_so.py:1056-1066`).
- Its only writer is `_redirect_row_if_received` (`app/services/project_order_inquiry_service.py:3466-3540`, the
  flag at `:3528`): on a replan (SO line qty/date change), a row whose PO/SPO link was already fully
  received is NOT restated; it is flagged used and kept as history, and a FRESH row is raised for the
  line's new need. That matches the 22 Sep split: 55 @ 31/12/2026 became 33 @ 04/05/2027 (fresh row on
  L256) + 22 @ 01/07/2027 (L416).
- The FE reads it as the grey "used" pill (`sorento_crm_frontend/app/(protected)/project-sales/order-inquiries/components/orderInquiryWorklistColumns.tsx:703-717`).
- A used row is history, not owed: the OI page's own fold treats it as not live
  (`app/(protected)/project-sales/_shared/lib/orderInquiryLineFold.ts:69-71`, `isLiveInquiryRow`), and the
  demand SQL excludes it (`app/services/scm/demand.py:375`).

## 2. Root cause (owner question 2): the snapshot offers the used row, the OI page does not

1. Snapshot "OI row" links every row on the SO line, used or not: `_linked_oi_rows`
   (`app/services/scm/stock_debt_snapshot_service.py:179-195`) joins `order_inquiry_rows` to the core line
   with no `redirected_to_pool` / `state` filter, both at save (`:115-121`) and at read (`lines()`, `:451-479`).
   Hence "55 33" on the OI-2609-0257 block.
2. The used row is reported requestable: `_oi_now` (`:538-552`) checks verb, state, open request and
   `_requestable`, never `redirected_to_pool`. `_requestable` (`app/services/order_inquiry_reserve_service.py:136-147`)
   adds back the qty on a fully received link, which is exactly what a used row carries, so the used 55
   row reads "55 left to request".
3. The drill's "Request CS to reserve" tick list (`SnapshotDrillDialog.tsx:156-181`, `OiRequestDialog`)
   keeps every drill row that passes `reserveIneligibleReason`
   (`app/(protected)/project-sales/_shared/lib/reserveEligibility.ts:33-50`), which has no used check. So
   Joey's tick list showed TWO rows for the one SRTSA830-PJ line: the used 55 row and the live 33 row.
   Both opened unticked because the line reads Short 0 (Pinned) (`SnapshotDrillDialog.tsx:206-213`), and
   nothing in the dialog marks either row as used. She ticked the 55 row and typed 33.
4. The server accepted it: `create_request` (`order_inquiry_reserve_service.py:706-730`) refuses wrong
   verb, wrong state, an open request and nothing left, but not a used row.
5. The OI page itself is safe: its Request dialog is fed only live rows (`OrderInquiryDetail.tsx:232-236`,
   `activeLines = lines.filter(isLiveInquiryRow)`). The snapshot copy is the only path that skips that.

So yes: she was shown the 55 row. Which of the two she meant cannot be read from code, but the dialog gave
her a used row to pick. Note it gets worse once #2145 (OI-ONE-DELIVERY-DATE) deploys: both rows then print
the SO line date (`app/services/oi_delivery_date.py`), so the two rows differ only by Remaining 55 vs 33.

Not the legacy duplicate-OI case: the 30 Oct detector (`PLAN-oi-legacy-dup-repair-30oct.md` section 2)
needs two sheet-import rows from one job; this is a replan redirect. The 30 Oct ruling ("snapshot freezes
SOs, not OIs", AC-RP-8) is what makes the drill re-read live rows; it just reads the used one too.

## 3. Why used rows show in Lines / Needs reserve (owner question 1)

- Order Inquiries > Lines (the worklist) shows every non-cancelled row, used included: the only default
  row filter is `state != cancelled` (`app/services/order_inquiry_worklist_service.py:1505-1511`).
- "Reserve: Needs reserve" keeps a row when one of ITS OWN request rows is unanswered
  (`order_inquiry_worklist_service.py:1520-1534`, predicate `order_inquiry_reserve_service.py:273-285`). The
  request sits on the used 55 row, so that is the row the filter shows. CS reserves against live supply,
  so they skip it, and the 33 is never answered (the 1 of 53 lines missing from the Reserved email).

## 4. Owner add-on: the drill "Now" pills, "OI row" links, "Covered by"

"Now" today (`SnapshotDrillDialog.tsx:74-97`), for OI-2609-0257 / SO396347:

| Pill | Source | Acted on? |
|---|---|---|
| Open 33 | SO status + live open qty of the SO line, `_line_now` (`stock_debt_snapshot_service.py:482-496`) | Yes: is the SO still owed |
| Raised (1st) | OI row state of the used 55 row, `_oi_now` `now_state` (`:545`), `stateLabel` | No: purchasing's state, and of a used row |
| Reserve requested | latest reserve request on the 55 row, `_oi_now` `latest` (`:517-536`), `RESERVE_LABEL` (`:63-68`) | Yes: tells who must act |
| Raised (2nd) | OI row state of the live 33 row | No |

One state pill plus one reserve pill per OI row, per line: two rows give four pills. Only the SO open qty
and the reserve state are things a person acts on here; the OI row state belongs on the OI page.

"OI row" (`SnapshotDrillDialog.tsx:113-135`): one link per OI row on the line, labelled with the row qty, to
`/project-sales/order-inquiries/<oi>?row=<row>`. "55" is the used row, "33" the live one.

"Covered by" (`app/(protected)/project-sales/stock-debt/lib/stockDebtDemandColumns.tsx:274-289`) prints one
entry per source; a line that lent landed goods gets one "Lent to SO... (n)" entry per receiver
(`app/services/scm/stock_debt_service.py:2455-2464`), so 4 receivers stretch the row to 4 wraps.

## 5. Proposed rules

- R1 (a): a used or cancelled row is never requestable. Server: `create_request` refuses it (409
  `reserve_request_used_row`), `_oi_now.requestable` false. FE: `reserveIneligibleReason` names it ("used,
  ask on the live row"). The drill's tick list then offers only the live row(s) of the line, the same set the
  OI page offers. No auto-redirect: with the used row gone, the only row offered IS the live one.
- R2 (c): snapshot "OI row" and "Now" read only live rows (not used, not cancelled), applied at READ time in
  `lines()`, so snapshots already saved (the 26/10 one included) are fixed too, not only new ones.
- R3 (owner add-on): "Now" collapses to ONE pill per line, first match wins:
  `SO cancelled` (red) > `Reserved N` (green, answered qty) > `Reserve requested N` / `Reserve parked N`
  (amber, requested qty) > `Open N` (neutral). "after the snapshot" moves to the OI row link's title.
  "OI row" links the live row only.
- R4 (owner add-on): "Covered by" with 2+ "Lent to" entries prints one entry `Lent to 4 SOs (47)`, a button
  opening the existing `Popover` with one linked line per SO. Own sources (On hand, PO, SPO) stay as today.
  Applies to the live drill and the snapshot drill (one shared column builder).
- R5 (b): Lines worklist hides used rows by default, behind a "Show used" filter (Q2).
- R6 (d): one-off repair script, dev first then prod by the owner: move each OPEN, unanswered request row
  sitting on a used row to the single live row of the same SO line in the same OI when its qty fits that
  row's requestable; otherwise hold and print the reason. Dry run default, `--apply --expect N`, idempotent
  (pattern of `scripts/repair_oi_legacy_dup_rows.py`).

## 6. Counts

Prod: read-only SQL for the owner, `SQL-oi-reserve-used-row-count-04nov.sql` beside this file.
Dev copy: `crew-data-request:` with the same SQL.

## 7. Workaround for CS today (no code)

On OI-2609-0257 (open it from Order Inquiries, not the snapshot): Actions > Cancel request (the open
request; it withdraws only its still-unanswered rows, so first check in the Reserve column that the
SRTSA830-PJ line is its only open row). Then Lines tab, tick the SRTSA830-PJ line (the page shows only
the live 33 @ 04/05/2027 row), Actions > Request CS to reserve, 33. Eling reserves that request as usual.
Do not request from the snapshot drill until R1 ships.

## 8. Test list (after answers; red first)

pytest: create_request refuses a used row (409 code); `_oi_now` used row requestable false; snapshot
`lines()` drops used/cancelled rows from `oi_rows` for a snapshot frozen before the row went used;
repair script dry run / apply / expect mismatch / idempotent / hold when 0 or 2 live rows / hold when qty
does not fit. vitest: `reserveIneligibleReason` used row; drill tick list without the used row;
NowCell one pill per precedence case; Covered by lent collapse at 1 vs 2+ receivers with popover list;
worklist used rows hidden by default and shown with the filter.
