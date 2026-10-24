# Behaviour card: per-SO remark in the Confirm purchasing email (FULFIL-SO-REMARK, 25 Oct 2026)

v2 (owner Lavish feedback on mock v1, 25 Oct 05:29): the remark is ONE word, `Sponsorship`,
`Purchase Request` or `Mockup`; normal SO blank; no per-line labels in the email.

Plan: `documentation/plans/scm/PLAN-fulfil-so-remark-25oct.md` (Step 1 findings, query results).
Mock: `documentation/mockups/FULFIL-SO-REMARK/index.html`.

## Rules (proposed)

1. Every SO page of the Confirm guide (Review split step, `ConfirmGuideDialog.tsx:273-407`) shows a
   **Remark** field under the SO header row: prefilled with the default, editable, clearable, up to
   100 characters.
2. The remark prints in a new **REMARK** column at the end of the email's SO table
   (S/O NO | SO DATE | CUSTOMER | PROJECT | REMARK). Blank remark, blank cell. The preview dry run and
   a resend show the same remark (both use `build_handover_email`, `project_order_inquiry_service.py:14202`,
   `oi_handover_resend.py:147`).
3. Default, part 1 (data the CRM already has): the SO's AutoCount Note contains `MOCK` (MOCKUP,
   MOCK UP, MOCK-UP, any case) -> `Mockup`; otherwise blank.
4. Default, part 2 (after the shared service pulls Refer Doc No, Shipping Info and the line remark),
   first match wins:
   1. Refer Doc No `PSSF...` or Shipping Info contains `SPON` -> `Sponsorship`.
   2. Refer Doc No `PR...` or Shipping Info contains `PURCHASE REQ` -> `Purchase Request`.
   3. Note contains `MOCK`, or any line remark contains `MOCK` (mixed SO) -> `Mockup`.
   4. Otherwise blank.
   Sponsorship / Purchase Request beat Mockup because the owner marked SO421287 (Sponsorship + Note
   mockup) `Sponsorship` and SO423072 (Purchase Request + Note mockup) `Purchase Request` on mock v1;
   a mixed SO is `Mockup` (owner on SO419417). No line prints a mockup label.
5. The remark is saved on the SO when Confirm sends the email. The next Confirm of the same SO
   prefills the saved remark, not a fresh default.

## Real examples (AutoCount, last 90 days; people masked)

| SO | Refer Doc No | Shipping Info | Note / lines | Default remark |
| --- | --- | --- | --- | --- |
| SO427088 | PS26-1784 | OT06/2702 (customer PO) | Note `***FOR MOCKUP` | `Mockup` (staff wrote `OTM / HUAZHI CONST. (MOCKUP)`) |
| SO427489 | PSSF26-0424 | SPONSORSHIP | no mockup | `Sponsorship` |
| SO423741 | PR26-0375 | PR26-0375 (the PR no, not the words) | Note `Only send 2 for mock up...` | `Purchase Request` |
| SO421287 | PSSF26-0381 | SPONSORSHIP | Note `***SPONSORSHIP (MOCKUP)***` | `Sponsorship` |
| SO419417 | PS26-0336 | U 2603-00010 | 3 of 24 lines: line remark `***FOR STH(100)-2 UNITS MOCK UP` (SRTWB1515, SRT2403-CR, CB2829-DIY) | `Mockup` |

Counts (810 project SOs): PR 40, Sponsorship 77, Note mockup 25, mixed by line remark 12 SOs / 21
lines, mockup header line 8 SOs, Note and line both 3.

## Edge cases

- Note talks about a PART of the SO in prose (SO423741, SO418716 `SUPPLIED 8 UNITS FOR MOCK UP`):
  default still says `Mockup`; staff edit the field.
- Mockup header line (a text-only AutoCount line `MOCKUP` / `MOCK UP - BLOCK 1` above the mockup
  items, 8 SOs): the shared service skips text-only lines (`presets.py:214`), so no auto flag; staff
  type it.
- Several flags on one SO: one word, first match of rule 4 (Sponsorship, then Purchase Request,
  then Mockup).
- Until part 2 ships, a Sponsorship / Purchase Request SO whose Note says mockup defaults to `Mockup`
  (part 1 cannot see the type: 15 such SOs in 90 days); staff edit the field.
- Edited, then Confirm again: the saved remark prefills (rule 5); a later AutoCount change does not
  overwrite it.
- Cleared field: blank cell, no default re-applied for that send.
- Customer names stay as they print today (CUSTOMER / PROJECT columns); the remark carries only the
  flag.

## Questions (each with a recommendation)

1. ANSWERED (owner, mock v1): normal SO blank.
2. PR / Sponsorship source: (a) Refer Doc No prefix OR Shipping Info words, (b) prefix only,
   (c) Shipping Info words only. **Recommend (a)**: of 40 PR-prefix SOs, 26 hold the PR number, not
   the words, in Shipping Info (words alone miss them); 8 SOs say SPONSORSHIP and 1 says PURCHASE
   REQ in Shipping Info with no PSSF / PR prefix (prefix alone misses them).
3. ANSWERED (owner, mock v1): mixed SO = `Mockup`, no line labels. Precedence when an SO is both a
   type and mockup: type wins (rule 4), read from the owner's notes on SO421287 / SO423072; confirm.
4. Confirm again: (a) prefill the saved remark (one new column on the project SO), (b) recompute the
   default every time (no column). **Recommend (a)**: a staff edit is not lost on the second
   Confirm.
5. Build order: (a) this PR = part 1 (field, email column, Note mockup default, saved remark; CRM
   only, size M); part 2 = a follow-up lane (shared-service SQL pull of RefDocNo / ShipInfo / line
   FurtherDescription + CRM columns + rule 4; size L, two repos), (b) both in one lane now.
   **Recommend (a)**: staff get the field this week with no shared-service dependency.
6. Field type: (a) free text input, prefilled with the one word, (b) a clearable select of the three
   words. **Recommend (a)**: the requirement says editable, and staff wrote other words in the past
   (e.g. a customer short name); the default still keeps to one word.
