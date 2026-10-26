# Behaviour card - AC-REMOVED-LINES: a line REMOVED in AutoCount releases its links

Lane AC-REMOVED-LINES, 26 Oct 2026. Code: origin/main bdb54371b1. Data: 20 Oct dev copy
(`sorento_prod_1020`), read-only. Plan: `PLAN-ac-removed-lines-26oct.md`.

## Removed is not cancelled

| AutoCount did | CRM today | After this lane |
| --- | --- | --- |
| Cancel PO / Cancel SO document, `qty_cancelled`, header cancel | line `cancelled`, links kept, red "PO cancelled" (LINKAGE-UNIFY Q5) | unchanged |
| Line DELETED (gone from the re-push) | line `cancelled` in place when anything points at it, every link kept (`document_ingest_service.py:1639-1657`; SPO: closed + `retired_at`, `shipping_order_ingest_service.py:557-579`) | line marked REMOVED, every link released |

## Rules

- R1 Marker. New `removed_at` on `purchase_order_lines` and `sales_order_lines`, set by the
  ingest sweep (`document_ingest_service.py:1639`) for an AutoCount line (has a DtlKey) whose
  header is not cancelled. `line_status` stays `cancelled` (keeps it out of demand and supply,
  as today). SPO keeps its existing marker `retired_at` (`shipping_order_ingest_service.py:578`).
  A DtlKey that comes back in a later push clears the marker (as `retired_at` already is,
  `shipping_order_ingest_service.py:1028`); released links are not restored.
- R2 PO or SPO line removed: every Order Inquiry link on it is released through the existing
  unlink path (`_remove_links`, `project_order_inquiry_service.py:13556`): the row's note gets
  "Unlinked from <PO>: line removed in AutoCount", its state recomputes (placed -> raised or
  partly linked; an `actioned` row keeps its state, `:9620`), it goes to To confirm
  (`ack_state = changed`, same handshake as `flag_rows_for_cancelled_lines`, `:968-1016`).
  Open order-link claims on the line are resolved; suggested links to it are dropped.
- R3 SO line removed: its live rows are released AND retired the way CS's Transfer to Cancel SO
  already retires them (`retire_rows_for_cancelled_lines`, `:5774`): placements go back to the
  PO/SPO, row `cancelled`, audit `OI_ROW_CANCELLED`, purchasing handover email. `actioned` rows
  are only flagged, as that function already does. Stock holds on the line
  (`so_line_allocations`, `models/project_so.py:1835`) are released.
- R4 Moved qty (the 546 case): when the same push leaves another line of the SAME document,
  SAME product with room, the released row gets a SUGGESTED link to it (existing
  `order_inquiry_suggested_links`, `models/project_so.py:1296`; worklist Suggested column,
  `orderInquiryWorklistColumns.tsx:485`). Never an automatic link: purchasing confirms it.
- R5 Never live supply: LINKAGE-UNIFY's chain (#1870, `scm/goods_chain.py` Q5 dead rule) reads a
  removed PO line / retired SPO line as dead, reasons "PO line removed" / "SPO line removed",
  received qty or not. Whichever PR merges second adds it; crew-note to that lane.
- R6 Reconciliation: the same release code, run once over existing removed lines by an admin
  script: dry run (counts + per-line list, no customer names) -> owner OK -> apply. Never by crew
  on prod.

## Real examples (20 Oct copy; PO 202607-S0081, all lines measured)

1. SRTSA-SS 546 (DtlKey 45713392) for SO396348: on 20 Oct closed, received 546, Placed 546.
   Removed after 20 Oct; prod shows it Cancelled, Placed 546. Its qty landed on the no-S/O
   SRTSA-SS line (DtlKey 45348511, 1,304 on 20 Oct, 1,850 on prod). After: link released,
   SO396348's row -> raised + To confirm, suggested link -> line 45348511 (R4).
2. SRTSA-SS 234 (45713393), received 0, cancelled 28 Sep, Placed 211 = SO382618 94 + SO396350
   117. After: both rows raised + To confirm, Placed 0.
3. SRTSA-SS 110 (45713391), received 0, cancelled 28 Sep, Placed 43 for SO396347.
4. SRTSA830-PJ 117 (45713386), RECEIVED 117, cancelled 28 Sep, Placed 117 for SO396350
   (a fully received removed line; same for SRTSA830-PJ 55, 45713384, Placed 55 SO396347).
5. SRTPW0035 58 + 58 (45520153/45520154), received 0, cancelled 30 Sep, Placed 31 + 53 for SO394876.

Scale (crew queries rerun on the 20 Oct copy): PO 91 removed AutoCount lines, 57 still linked
(30 with placements, 4,015 placed; 49 booked for an open SO line). SPO 259 retired, 6 with
placements (659). SO 380 removed lines, 73 live OI rows, 2 with placements (7). UNVERIFIED: the
crew claim that the 64 raised rows still count as buy demand; the worklist Buy already owes 0 on
a cancelled line (`order_inquiry_worklist_service.py:3109-3129`).

## Edge cases

- Partly or fully received removed line (examples 1, 4): released all the same; the receipt
  stays on the removed line as evidence; supply ignores it (R5).
- Removed PO line with an SPO transfer under its key: released, and the SPO line is offered as
  the suggested link (R4); 0 such lines on the 20 Oct copy.
- SO line removed while its PO line is live: placement released, the PO qty becomes free; the PO
  line's own S/O (AutoCount's `from_so_line_ref`) is AutoCount's data and is left; 0 open PO lines
  booked for a removed SO line on the 20 Oct copy.
- Out of scope, left as they are: Cancel PO/SO documents, header cancels, the CS Cancel SO board,
  goods received (`picking_lines`), moved stock transfers, loading plans, xlsx-era ref-less lines
  replaced at adoption (Q4).

## Questions (recommendation first)

- Q1 SO line removed, its rows: (a) retired like Transfer to Cancel SO (R3: placements back,
  audit, purchasing email) / (b) links released, row stays live in To confirm, owing 0.
  Rec (a): the demand is gone, and that mechanism exists and is what CS's cancel already uses.
- Q2 PO/SPO line removed, how purchasing hears: (a) To confirm + row note + audit, no email
  (R2) / (b) (a) plus an email per push. Rec (a): To confirm is purchasing's inbox for
  ingest-driven changes (owner ruling C1, `PLAN-oi-cancelled-line-used-confirm.md` section 2).
- Q3 Moved qty: (a) suggested link to the same document's same-product line, purchasing confirms
  (R4) / (b) no proposal, purchasing relinks from the Link dialog. Rec (a): explicit, no
  auto-linking, reuses suggested links.
- Q4 Reconciliation scope: (a) AutoCount lines only (PO 57 / SO 73 rows / SPO 6), admin script
  dry run -> owner OK -> apply / (b) also the xlsx-era ref-less leftovers (PO 5,592 lines with 996
  open claims; SO 10,651 lines with 290 live rows). Rec (a): those were replaced at adoption, not
  removed by AutoCount; separate lane if wanted.
- Q5 Display: (a) grey "Removed" status on the PO/SO line (distinct from red Cancelled), Placed 0
  after release, S/O cell as is; mock follows your answers / (b) hide removed lines from the
  document. Rec (a): the evidence stays visible.
