# PLAN: one standard History view for every audited record (STANDARD-HISTORY)

Status: wave 1 (#2299) built and crew-passed, NOT accepted by the owner on hand test (10 Nov
~15:10 MYT: "OI history why so complicated geh, our other audit trails or history page also so
complicated? i want to reuse same component though"). Mock v2 (simple, one component =
`AuditTrail`) filed as `crew-ask`: `mockups/standard-history-v2-10nov.html`, comparison
screenshots in `evidence/standard-history-compare/`. #2299 is frozen until the owner approves v2.
Part A (an Unconfirm guard) was dropped by the owner on 10 Nov ~12:50.

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

## Owner hand test of wave 1, and v2 (10 Nov ~15:10)

Verdict: too complicated; reuse the same component. Cause, from the comparison
(`evidence/standard-history-compare/`): v1 copied the busiest history in the system (the
planning-admin SO drawer: five filters, Clear, a badge per event, a grid per batch) instead of
the simple one already on 8 detail pages (`components/audit/AuditTrail.tsx`: one entry per
change, what / when / who, then indented change lines). v2 makes `AuditTrail` the one component:
a plain two-line entry (one sentence; dd/mm/yyyy time and person), details only on "Show N
lines", one search box shown only past 10 entries, no filters or badges. The backend endpoint
and the OI root stamp stay as built.
