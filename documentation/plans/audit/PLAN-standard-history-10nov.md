# PLAN: one standard History view for every audited record (STANDARD-HISTORY)

Status: Part A built on PR #2298 (small fix track: FE only, no migration, no RBAC change). Part B
scout is filed as a `crew-ask` card on PR #2298; Part B is not built until the owner approves the
proposal and the mock.

Plan created: 2026-11-10. Domain: audit. UAC: `standard-history-10nov-acceptance-criteria.md`.

## Journey

Owner, 10 Nov ~11:30 MYT: "we need to show a history for this, ideally all history that we keep
track of, we should visualize it at the frontend in a standard way for ppl to see and check".

Trigger case (prod, the owner's read-only query): OI-2611-0019 (SO428916). On 9 Nov 17:15:45 MYT
Joey pressed Confirm on 1 row (SRTSP131, marked Done by hand). 8 s later she pressed Unconfirm
with nothing ticked, and every one of the 9 confirmed rows went back to "To order · manual".

- The OI line History dialog (`OrderInquiryLineHistoryDialog.tsx`, Rows / Decisions / Reserve
  tabs) never shows Confirm / Unconfirm presses. They live only in `audit_logs`
  (`project_order_inquiry_service.py:9678-9688`, `:9849-9866`; the batch row's `entity_id` is the
  first row id, and `new_values.row_ids` holds every row).
- The status pill's native `title` (`OrderInquiryLineStatusPill.tsx:81`) is the only place that
  reads "Unconfirmed by <name>, <date>".
- The whole-OI Unconfirm had no guard (`OrderInquiryDetail.tsx:283-291`, `:670-675`, `:868-874`).

## Part A: Unconfirm never widens to the whole OI (built)

Decision: **disable until lines are ticked**, not an "Unconfirm all N lines?" dialog, because:

- It is what every other bulk action does: the worklist's `Unconfirm (N)`
  (`OrderInquiriesClient.tsx:1910-1928`, disabled with "Tick rows purchasing has already
  confirmed."), and this page's `Link selected` / `Unlink selected` / `Reject selected`.
- `PRINCIPLES.md` design mandates and `ADR-PRODUCT-STANDARDS.md` rule out confirmation dialogs.
- Unconfirming the whole OI is still two clicks: tick the header checkbox, press Unconfirm.

This supersedes the coordinator's "W" ruling (nothing ticked = every confirmed line of the OI).
Confirm and Auto link keep their whole-OI fallback: they move rows forward, and nobody asked to
change them.

Change: `OrderInquiryDetail.tsx` `unconfirmScope = selectedUnconfirmable` (the whole-OI
`allUnconfirmable` branch is removed). Tests: `OrderInquiryDetail.test.tsx` "STANDARD-HISTORY A"
(nothing ticked: disabled, no call; one line ticked: sends that line's live confirmed row only,
never its cancelled or used rows). It replaces the Review S3 test, which pinned the whole-OI
behaviour.

## Part B: standard History view (proposal, awaiting owner)

Steps: (1) a scout report filed as `crew-ask`; (2) one reusable component proposal mapped onto
existing components; (3) a mock built on the OI-2611-0019 case, committed as static HTML, built
only after the owner approves; (4) rollout waves, each wave its own PR: OI detail + OI line, then
SO / Fulfilment Planning, contacts and dealer access, products / spec registry, price tags, then
the rest.

Rules: dd/mm/yyyy dates; one line per row in the standard DataGrid; never another company's data
(redact as #2295 does); no new write paths; red-first tests, kill tests, reviewer, security review
(audit data exposure), browser pass, hand-test scripts.

Existing work this builds on, not around: `documentation/plans/audit/PLAN-audit-standard-26sep.md`
(the append-only `audit_logs` backbone), `PLAN-audit-trail-diff-27oct.md` and
`PLAN-audit-trail-resubmitted-28oct.md` (`components/audit/AuditTrail.tsx`, the per-record trail
already shown on several detail pages).
