# Behaviour card: per-SO remark in the Confirm purchasing email (FULFIL-SO-REMARK, 25 Oct 2026)

v2 (owner Lavish feedback on mock v1, 25 Oct 05:29): the remark is ONE word, `Sponsorship`,
`Purchase Request` or `Mockup`; normal SO blank.

**FINAL (owner rulings 25 Oct ~05:35 on card v2):** Q1 normal SO blank. Q2 source = Shipping Info
words, not the Refer Doc No prefix. Q3 mixed SO = SO remark `Mockup` AND a `Mockup` label on each
flagged line, on the split page and in the email. Q4 recompute the default every time the Confirm
guide opens; no saved-remark column. Q5 both parts now: shared-service SQL preset adds ShipInfo,
line FurtherDescription and the text-only MOCKUP heading; CRM stores them; RefDocNo not needed.
Q6 free text prefilled with the word, editable. Size L (shared-service PR + CRM PR).
Refined by owner mock v2 feedback (05:34): Mockup and the line labels are decided from the lines
CHOSEN in this Confirm (rules 3-5, cases table).

Plan: `documentation/plans/scm/PLAN-fulfil-so-remark-25oct.md` (Step 1 findings, query results).
Mock: `documentation/mockups/FULFIL-SO-REMARK/index.html`.

## Rules (final)

1. Every SO page of the Confirm guide (Review split step, `ConfirmGuideDialog.tsx:273-407`) shows a
   **Remark** field under the SO header row: free text, prefilled with the default, editable,
   clearable, up to 100 characters.
2. The remark prints in a new **REMARK** column at the end of the email's SO table
   (S/O NO | SO DATE | CUSTOMER | PROJECT | REMARK). Blank remark, blank cell.
3. Default, recomputed every time the Confirm guide opens, from the LINES CHOSEN for that SO in
   this Confirm (an edit applies to that send only), first match wins:
   1. Shipping Info contains `SPON` (any case) -> `Sponsorship`.
   2. Shipping Info contains `PURCHASE REQ` (any case), or starts with `PR` followed by a digit
      (a PR number such as `PR26-0375`; owner approved 25 Oct 05:39, may drop it) -> `Purchase Request`.
   3. At least one chosen line is a mockup line (rule 4) -> `Mockup`.
   4. Otherwise blank (also when the SO has mockup lines but none of them is chosen this time).
   Sponsorship / Purchase Request stay SO-level and beat Mockup: the owner marked SO421287
   (Sponsorship + Note mockup) `Sponsorship` and SO423072 (Purchase Request + Note mockup)
   `Purchase Request` on mock v1.
4. A line is a **mockup line** when the SO's Note contains `MOCK` (MOCKUP, MOCK UP, MOCK-UP, any
   case: the whole SO is mockup, so every line is), or its AutoCount line remark
   (`SODTL.FurtherDescription`) contains `MOCK`, or it sits under a text-only heading line whose text
   contains `MOCK` (the heading covers the item lines after it, up to the next text-only line with
   text).
5. Line labels (owner, mock v2 feedback 05:34): only when the chosen lines MIX mockup and actual
   lines does each chosen mockup line get a `Mockup` badge on the split page and `Mockup` in the
   email line REMARK cell, ahead of any text the cell already holds (`Mockup, <text>`). Chosen lines
   all mockup, or none mockup: no line labels. The label is independent of the SO word (a Purchase
   Request SO with mixed chosen lines still labels its mockup lines).

6. **Sales Order page** (owner 25 Oct ~13:05): Project Sales Admin > Sales Orders > SO detail.
   The General tab shows two read-only fields: `Remark` = rule 3 computed over ALL live lines of the SO (cancelled lines skipped, like the order
   total; crew ruling 25 Oct, owner may override)
   (not a Confirm choice; nothing is stored) and `Shipping Info` as stored from AutoCount. The Lines
   tab shows a `Mockup` label on each mockup line only when the SO's lines mix mockup and actual
   (rule 5 over all lines). Same rules function as the guide and the email.

## Cases (one example each; SO419417 = 24 lines, 3 of them line-remarked mockup: SRTWB1515, SRT2403-CR, CB2829-DIY)

| Case | Example | SO remark | Line labels |
| --- | --- | --- | --- |
| Chosen lines mix mockup + actual | SO419417, all 24 lines chosen | `Mockup` | `Mockup` on SRTWB1515, SRT2403-CR, CB2829-DIY |
| Chosen lines all mockup (part of a mixed SO) | SO419417, only those 3 lines chosen | `Mockup` | none |
| Chosen lines none mockup | SO419417, only the 21 other lines chosen | blank | none |
| Whole SO mockup by Note | SO427088 (Note `***FOR MOCKUP`), any lines | `Mockup` | none (every line is mockup) |
| Sponsorship | SO427489 (Shipping Info SPONSORSHIP) | `Sponsorship` | none |
| Sponsorship + whole-SO mockup | SO421287 (Note `***SPONSORSHIP (MOCKUP)***`) | `Sponsorship` | none |
| Purchase Request | SO427488 (Shipping Info PURCHASE REQUEST) | `Purchase Request` | none |
| Normal | SO424062 | blank | none |

## Real examples (AutoCount, last 90 days; people masked)

| SO | Refer Doc No | Shipping Info | Note / lines | Default remark |
| --- | --- | --- | --- | --- |
| SO427088 | PS26-1784 | OT06/2702 (customer PO) | Note `***FOR MOCKUP` | `Mockup` (staff wrote `OTM / HUAZHI CONST. (MOCKUP)`) |
| SO427489 | PSSF26-0424 | SPONSORSHIP | no mockup | `Sponsorship` |
| SO423741 | PR26-0375 | PR26-0375 (the PR no, not the words) | Note `Only send 2 for mock up...` | `Purchase Request` (PR-number pattern) |
| SO421287 | PSSF26-0381 | SPONSORSHIP | Note `***SPONSORSHIP (MOCKUP)***` | `Sponsorship` |
| SO419417 | PS26-0336 | U 2603-00010 | 3 of 24 lines: line remark `***FOR STH(100)-2 UNITS MOCK UP` (SRTWB1515, SRT2403-CR, CB2829-DIY) | `Mockup`; those 3 lines labelled `Mockup` |

Counts (810 project SOs): PR 40, Sponsorship 77, Note mockup 25, mixed by line remark 12 SOs / 21
lines, mockup header line 8 SOs, Note and line both 3.

## Edge cases

- Note talks about a PART of the SO in prose (SO423741, SO418716 `SUPPLIED 8 UNITS FOR MOCK UP`):
  default still says `Mockup`; staff edit the field.
- Several flags on one SO: one word, first match of rule 3 (Sponsorship, then Purchase Request,
  then Mockup). Line labels follow rule 5 whatever the SO word is.
- Staff confirm the mockup lines first and the actual lines another time: the first send says
  `Mockup` (no labels), the second says blank (rule 3.4).
- Shipping Info holds a PR number instead of the words (26 of 40 PR SOs in 90 days, e.g.
  `PR26-0375`): covered by rule 3.2's PR-number pattern. `PRR26-...` (4 SOs) does not match.
- Confirm again, or the guide reopened: the default is computed again from the current AutoCount
  data; an earlier edit is not kept.
- Cleared field: blank cell for that send.
- Customer names stay as they print today (CUSTOMER / PROJECT columns); the remark carries only the
  flag.
- Old SOs pulled before the shared-service change have no Shipping Info / line remark / heading in
  the CRM until their next pull; their default comes from the Note only.

## Questions

All answered by the owner, 25 Oct (see FINAL above). Mock v3 approved 05:39.
