# PLAN: Stock Debt snapshot, link a PO line to an SO line via AutoCount (AC-LINK-CRM-UI)

Status: PR+CI (mock v4 approved 4 Nov; Q1 snapshot only, Q3 SS infers whole row vs split; built, reviewer READY; unlink countdown owed before SS enables unlink_row). Track: full (SIZE M, new action on an existing screen).

Lane: AC-LINK-CRM-UI. Mock: `ac-link-crm-ui-04nov-mockup.html` (this folder).

## Behaviour card

### Where it lives

Recommendation: **Stock Debt snapshot drill only** for this lane. Project sales > Stock Debt >
Snapshots > a snapshot > press a month cell opens `SnapshotDrillDialog`
(`sorento_crm_frontend/app/(protected)/project-sales/stock-debt/components/SnapshotDrillDialog.tsx`).
Each SO line row gets a "PO link" menu beside the existing "Request CS to reserve" toolbar button
(`SnapshotDrillDialog.tsx:216-230`). That is the screen purchasing already decides on (Decision =
Reserve / Buy / Ignore), it already shows the PO line covering each SO line (Covered by, R42,
`stockDebtDemandColumns.tsx:407`), and the snapshot freezes SOs, which is what a link points at.

Not on the OI screen in this lane: the OI page is CS's screen (reserve requests); a PO link is a
purchasing decision. The dialog is a shared component, so adding it to the OI screen later is one
mount.

Later CRM lanes (not this lane), project-sales QT / SO triggers:
- Quotation accepted: offer "link to PO line" for lines purchasing already bought ahead (needs QT write in SS, lane AC-WRITE-QTSO).
- Sales order created from a project: auto-propose the reserve PO line at the SO's location as a split-link, purchasing confirms.
- SO line qty or location changed: flag the linked PO line as mismatched and offer relink.
- SO cancelled: offer unlink (enabled once AutoCount's DELETE ships).

### Rules

1. The CRM decides intent: which PO line, which SO line, qty, location. SS performs the steps.
   AutoCount stays the source of truth.
2. Four operations, each one row action: **Link whole row**, **Split-link**, **Unlink**,
   **Relink to another SO**. Each is enabled or disabled by the SS capability feed, read at
   runtime when the menu opens (cached a few minutes on the BE), never hardcoded. A disabled
   action shows the feed's reason ("Waiting for AutoCount: ..."). Nothing is hidden.
3. The CRM picks the operation from the PO line chosen: same location and qty = the PO line's
   whole free qty and the row is unlinked -> Link whole row; otherwise -> Split-link (deduct qty
   from the PO line, new PO line at the SO line's location linked to the SO line).
4. Picker lists only open PO lines for the same product with free qty > 0. Used rows (fully
   linked or received) are never shown or requestable. Qty defaults to the SO line's outstanding,
   capped at the PO line's free qty; integer, min 1.
5. Every write is followed by a GET back. The dialog shows what AutoCount returned, line by line.
6. Delete + create changes DtlKeys: after any write the snapshot line re-points to the
   fetched-back rows (new PO line id / DtlKey). The frozen demand stays frozen; only the link
   (Covered by, Short, Now) reflects the new rows.
7. Outcomes: done -> green read-back; done-with-warning `LOCATION_NOT_MOVED` -> amber, read-back
   shown, "Retry location"; `VENDOR_UNSUPPORTED` -> red "AutoCount refused", nothing changed;
   partial (step 1 done, step 2 failed) -> red with the read-back and "Retry step 2". Never a
   silent failure.
8. Environment gate: writes are db3-only (SS guard). The CRM button is enabled only when the
   capability feed says writes are allowed for the company this CRM talks to; on any other
   environment it stays visible and disabled with the feed's reason. No CRM env flag of its own
   (SS's guard is the single gate).
9. Permission: a new `projects.stock_debt.link_po` slug (purchasing roles). Without it the
   menu is not rendered.
10. Dates dd/mm/yyyy; picker columns all sortable; Location and Supplier filters multi-select.

### Examples (cloud sandbox has no prod copy; codes from repo fixtures, numbers illustrative)

1. SO419208 line 2, SRTWB242, 120 at MWH-BB, short 120. Pick PO 202609-S0029 line 3 at HQ,
   free 380 -> Split-link: line 3 500 -> 380, new line 120 at MWH-BB linked to SO419208 line 2.
2. Same SO line, pick PO 202610-S0007 line 1 at MWH-BB, free 120 -> Link whole row, disabled
   today ("waiting for AutoCount").
3. SO407114 line 1 already on PO 202609-S0029 line 4 -> Unlink / Relink disabled today.
4. SO396071 line 4 covered from on hand BRW-BB -> no PO actions.
5. Split-link where AutoCount creates the new line at HQ -> amber LOCATION_NOT_MOVED + Retry.

### Edge cases

- PO line changed in AutoCount since the snapshot: the picker reads live free qty; a stale qty
  is refused by SS and shown.
- SO line cancelled / missing since the snapshot (Now = SO cancelled): actions disabled.
- Double submit: the button locks while the call runs; the BE refuses a second write for the
  same SO line while one is in flight.
- Capability feed unreachable: every action disabled, reason "Could not reach AutoCount".

### Contract assumed (not verified: this sandbox cannot read foundryx-shared-service)

`GET capabilities` -> per operation `{available, reason}` plus a writes-allowed flag;
`POST` link / split / unlink / relink -> steps + read-back rows with new DtlKeys; warning code
`LOCATION_NOT_MOVED`; refusal code `VENDOR_UNSUPPORTED`. To be pinned against SS PR #183 and the
AC-WRITE-QTSO lane before Phase 2.

## Rulings (4 Nov) and mock v2

- Q2: new slug `projects.stock_debt.link_po` + Admin grant sweep.
- Q4: SS owns steps and recovery (SS PR #191). The CRM shows SS's outcome and offers Resume
  (`POST /write-operations/{id}/resume`); it never re-sends a step.
- Q5: contract pinned to SS PR #191 `documentation/plans/sprint-5/57-autocount-write-qtso-contract.md`.
- Owner Lavish feedback on v1, applied in v2: tick rows first, then one "Decide (N)" dropdown
  (Request CS to reserve, Link to PO, Unlink from PO, Move PO to another sales order); popup with
  checkboxes like Request CS to reserve; PO number and line shown separately; Bin renamed
  Location; Delivery date shown; "Would be" column dropped; plain wording, no system terms.
- Owner Lavish note on v2 ("need to show the PO qty here also", Outstanding header), applied in v3:
  drill gains "PO qty" (qty of the PO lines covering the SO line) beside Outstanding; the Link to PO
  popup gains "PO qty" (the picked PO line's qty) and "Free" beside Outstanding.

## SS contract (PR #191, pinned)

- Link: `POST /api/v1/autocount/po-links` `{companyCode, poDocKey, poDtlKey, soDocKey, soDtlKey, qty, soDocDate?}`
  + `Idempotency-Key`. SS decides whole row (qty = PO row qty: delete + add, `replacedLines`) vs part
  (split). So the CRM sends intent only; it does not pick the mode (this also answers Q3 in practice:
  the user never chooses).
- Unlink: `POST /po-links/unlink` `{companyCode, poDocKey, poDtlKey}`. Move: `POST /po-links/relink`
  `{companyCode, poDocKey, poDtlKey, soDocKey, soDtlKey, docDate?, soDocDate?}` (Idempotency-Key required).
- Answer: `{operationId, outcome, errorCode, message, warnings, docKey, docNo, replacedLines, document}`.
  outcome: done (200) / refused (403/409/422) / pending_verification (202) / vendor_error, mismatch,
  recovered, needs_attention (502). Resume: `POST /write-operations/{id}/resume {companyCode}`.
- `replacedLines` [{oldDtlKey, newDtlKey}]: the CRM moves the snapshot line's PO link to the new row.
- Capabilities: `GET /write-capabilities?companyCode=` -> `{capabilities:[{op, kind, enabled, reasonCode}]}`.
  Whole-row link = `link_row/PO`, unlink = `unlink_row/PO`, move = `relink_row/PO`. Part-row link has no
  own entry: the CRM reads it as PO `add_line` and `edit_doc` both enabled (gap raised with AC-WRITE-QTSO).
  reasonCode -> wording: VENDOR_UNSUPPORTED "Waiting for AutoCount"; WRITE_DISABLED / WRITE_NOT_ALLOWED
  "Changes to AutoCount are switched off here" (this is the per-environment gate; db3-only today).
- Result wording (UI): done "Linked: SO425045 line 140 now covered by PO 202609-S0029";
  LOCATION_NOT_MOVED "Linked, still at HQ" + "Move to <location>" (SS `/po-links/relocate`);
  refused VENDOR_UNSUPPORTED "Not linked: AutoCount cannot do this yet. Nothing was changed.";
  needs_attention "Needs attention" + Resume.
