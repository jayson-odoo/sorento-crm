# UAC: AutoCount end to end on db3 (AC-E2E-DB3)

Plan: `PLAN-ac-e2e-db3-06nov.md`. Every row is driven from the real CRM UI on the db3 staging stack and
checked against AutoCount's own read API (hapi db3), not CRM state alone.

## Writes that must work

| ID | Operation (CRM screen) | Pass when |
| --- | --- | --- |
| E1 | PO line link to an SO line, same location (Stock Debt > drill > PO actions > Link) | AutoCount PO row carries the SO's FromDocNo/FromDocDtlKey; qty unchanged; other rows untouched; CRM shows the link |
| E2 | Split link: big PO line at HQ to a smaller SO line at another location | AutoCount PO line qty reduced by the linked qty; a new PO row linked to the SO row at the SO row's location (relocate); totals unchanged |
| E3 | SPO line link to an SO line | AutoCount SPO row linked to the SO row; CRM shows it |
| E4 | Quotation create (project sales > quotation > Create in AutoCount) | AutoCount has a new QT with the CRM lines, debtor, displayTerm from the debtor; CRM stores the DocNo |
| E5 | Quotation update | AutoCount QT lines/fields reflect the edit; no duplicate rows |
| E6 | Sales order create (project sales > sales order > Create in AutoCount) | AutoCount has a new SO matching the CRM; CRM stores the DocNo |
| E7 | Sales order update (amend) | AutoCount SO reflects the amendment; no duplicate rows |

## Refusals that must happen before any write

| ID | Operation | Pass when |
| --- | --- | --- |
| R1 | SO cancel | Refused or greyed per `/write-capabilities` (cancel ships OFF); AutoCount SO unchanged |
| R2 | Whole-row link (existing PO row to SO row without split) | Refused `VENDOR_UNSUPPORTED` (or greyed); AutoCount unchanged |
| R3 | Unlink a PO row | Refused `VENDOR_UNSUPPORTED` (or greyed); AutoCount unchanged |
| R4 | SPO unlink | Refused `VENDOR_UNSUPPORTED` (or greyed); AutoCount unchanged |
| R5 | Delete line / delete doc | Not offered or refused; AutoCount unchanged |
| R6 | Debtor with no credit term | QT/SO create refused "AutoCount needs a credit term on debtor <code>..."; nothing written |

## Read-back after the writes

| ID | Check | Pass when |
| --- | --- | --- |
| P1 | AutoCount -> SS -> CRM pull of every written doc | Each doc in CRM once, lines match AutoCount rows, no duplicate lines |
| P2 | Amended SO (E7) after the pull | No line is marked "removed in AutoCount" falsely (AC-REKEY-SAME-LINE #2219) |

## Evidence per row

Doc numbers, screenshot, hapi GET read-back (before/after), CRM state. PASS/FAIL table in
`documentation/integrations/autocount/test-report-2026-11-06-e2e-db3.md`.

## Phase 2 (SS write API v2, 11 Nov 2026)

SS now offers whole-row link, change link and unlink for PO rows, and cancel / delete line for QT, SO and PO. Rows
R1, R2, R3 and R5 above move to "must work"; only SPO operations (R4) stay refused (`VENDOR_UNSUPPORTED`).

| ID | Operation | Pass when |
| --- | --- | --- |
| L1 | Link an existing whole PO row to an SO row (Stock Debt > Link to PO, qty = the row's qty) | AutoCount row carries FromSODtlKey of the SO row (DtlKey may change); other rows untouched; price/date kept |
| L1b | Same, SO row at another location | the linked row sits at the SO row's location |
| L2 | Change link (Move PO to another sales order) | the PO row's FromSODtlKey is the new SO row |
| L3 | Unlink | the PO row has FromSODtlKey 0 and keeps qty, price, date |
| L4 | Split link (regression) | as E1/E2, price and date kept on the new row |
| P2 | Pull back | one open CRM line per AutoCount row, link refs right, no line wrongly marked removed |
| Q1-Q3 | QT/SO cancel, remove line (incl. the last line), edit + add rows | after #2173 is updated (lane AC-QTSO-CRM-2) |
