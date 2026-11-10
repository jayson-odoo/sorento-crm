# PLAN: one standard History view for every audited record (STANDARD-HISTORY)

Status: Part B wave 1 in build on PR #2299 (track: full, an auth-adjacent read of audit data).
Part A (an Unconfirm guard) was DROPPED by the owner on 10 Nov ~12:50 MYT ("just drop the
unconfirm thingy, I didn't say I want this"); its code and tests are reverted and Unconfirm with
nothing ticked keeps today's behaviour. Scout done, owner answered Q1 to Q4, mock v1 approved
12:41 on condition that only existing components are used.

## Owner rulings (10 Nov 2026 ~12:40 MYT, via crew)

- Q1: History is a TAB on each record's detail page, "1 tab just like SO or PO", the same
  component as the PO detail History tab. Not a gear drawer. Where a record has no tabs, the mock
  says so and proposes the smallest fit.
- Q2: anyone who can open the record sees its history; IP and raw data stay admin-only.
- Q3: yes, the OI Confirm / Unconfirm audit writes also stamp the OI as root.
- Q4: the real OI-2611-0019 story, person names masked.

Plan created: 2026-11-10. Domain: audit. UAC: `standard-history-10nov-acceptance-criteria.md`.

## Journey

Owner, 10 Nov ~11:30 MYT: "we need to show a history for this, ideally all history that we keep
track of, we should visualize it at the frontend in a standard way for ppl to see and check".

Trigger case (prod, the owner's read-only query): OI-2611-0019 (SO428916). On 9 Nov 17:15:45 MYT
J*** (Purchasing) pressed Confirm on 1 row (SRTSP131, marked Done by hand). 8 s later she pressed Unconfirm
with nothing ticked, and every one of the 9 confirmed rows went back to "To order · manual".

- The OI line History dialog (`OrderInquiryLineHistoryDialog.tsx`, Rows / Decisions / Reserve
  tabs) never shows Confirm / Unconfirm presses. They live only in `audit_logs`
  (`project_order_inquiry_service.py:9678-9688`, `:9849-9866`; the batch row's `entity_id` is the
  first row id, and `new_values.row_ids` holds every row).
- The status pill's native `title` (`OrderInquiryLineStatusPill.tsx:81`) is the only place that
  reads "Unconfirmed by <name>, <date>".

## Part B: standard History view (approved 10 Nov 12:41, existing components only)

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

## Mock data: OI-2611-0019 (crew, 10 Nov 2026, from the owner's prod read-only query)

Q4 answered by crew: use the real item codes and times; person names stay masked in the repo
("J*** (Purchasing)"). The mock is built only after the owner answers Q1 to Q3.

- Header: OI-2611-0019, SO428916. Raised 02/11/2026 17:31 by A*** (CS).
- 09/11/2026 17:15:45 MYT, J*** (Purchasing): Confirm, 1 row marked Done by hand (SRTSP131).
- 09/11/2026 17:15:53 MYT, J*** (Purchasing): Unconfirm, 9 rows back to To confirm (one batch
  entry, one line per row):

| Item | Qty | Link at the time |
|---|---|---|
| CKS1050 | order back 4 | PO 202609-S0107 |
| CKSW015 | order back 4 | no link |
| SRT61-CR | 10 | PO 202610-S0015 |
| SRTHD122 | 3 | PO 202609-S0013 |
| SRTSH22512-N | 1 | PO 202608-S0015 |
| SRTWC286-SH-NEW | order back 7 | PO 202609-S0032 (closed) + SPO |
| SRTWT167 | 14 | PO 202610-S0041 |
| SRTWT2219 | 4 | PO 202610-S0015 |
| SRTSP131 | | Done by hand 8 s earlier |

- 10/11/2026 10:52 MYT: PO 202611-S0027 linked to SRTSP131, which went Done automatically.
- Untouched by the Unconfirm: SRT320-CR (10), SRT5674-N, SRT5732, SRTWB246 (raised, request to
  reserve).

## Wave 1 build notes (PR #2299)

- Built only from existing components (owner 12:41). `components/history/RecordHistory.tsx` is
  the SO History drawer's body (`PlanningHistorySheet.tsx`) lifted out of its Sheet; the swap
  list from mock v1 is in the PR description.
- Read gate: `projects.projects.view`, staff sessions only (an X-API-Key principal is refused,
  the PO-history ruling for audit reads). Admin extras (IP, raw values) are not in wave 1.
- **Deferred, with its trigger: a GIN index on `audit_logs (new_values->'row_ids')`** (partial,
  `entity_type IN ('project_order_inquiry_rows','order_inquiry_rows')`). The History read finds a
  press through that path, which today is a filter over every OI-row audit row (reviewer: 179 ms
  at 100k such rows on 1M, 0.08 ms with the index). OI rows are `__audit_skip__`, so the set
  grows only by Confirm / Unconfirm presses and row cancellations. Trigger: when
  `SELECT count(*) FROM audit_logs WHERE entity_type IN ('project_order_inquiry_rows',
  'order_inquiry_rows')` passes 50,000 on prod, add the index in its own migration (CREATE INDEX
  CONCURRENTLY). Nobody in this lane can read prod; the owner or crew runs the count.
- Wave 2 (SO / Fulfilment Planning): make `PlanningHistorySheet` render `RecordHistory` (it needs
  an SO filter, per-kind columns, per-event extras such as "Open email", an alert dot tone and
  item-code line matching), and pull `_ROW_AUDIT_TYPES` / the 5 s raise window / `_iso` into one
  backend helper shared with `planning_history_service.py`.
