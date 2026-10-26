# PLAN - lines removed in AutoCount release their links (PO, SPO, SO)

Status: PLANNING, 26 Oct 2026. Lane AC-REMOVED-LINES, branch `crew/ac-removed-lines`. Size L
(migration + ingest behaviour + prod reconciliation), lead pattern. Behaviour card filed to the
owner before any code: `ac-removed-lines-behaviour-card.md`. UAC:
`ac-removed-lines-26oct-acceptance-criteria.md` (written after the card's answers).

## 0. What the owner saw (prod, 26 Oct 2026)

PO 202607-S0081, SRTSA-SS line of 546 booked for SO396348: the CRM shows it "Cancelled" with
Placed 546, but the line no longer exists in AutoCount's PODTL. AutoCount moved the qty onto the
document's no-S/O SRTSA-SS line (1,304 on the 20 Oct copy, 1,850 on prod).

Ruling (owner, 26 Oct ~16:25): a line REMOVED (deleted) in AutoCount RELEASES every link the CRM
holds on it, for PO, SO and SPO lines alike. This is distinct from a line CANCELLED in AutoCount
(Cancel PO / Cancel SO documents, `qty_cancelled`, header cancel), which keeps its placement and
shows red "PO cancelled" (LINKAGE-UNIFY Q5). Those paths are left exactly as they are.

## 1. Measured (origin/main bdb54371b1; 20 Oct dev copy `sorento_prod_1020`)

To be completed from the research pass; see the card for the counts and examples.

## 2. Design

To be completed after the card's answers.

## 3. Tickets / slices

To be completed after the card's answers.
