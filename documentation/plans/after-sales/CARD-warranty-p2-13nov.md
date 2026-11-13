# CARD: After-sales P2, warranty (is this covered?)

Status: behaviour card v1, filed as a crew-ask on the P2 PR. No code until the owner answers.
Plan: `PLAN-warranty-p2-12nov.md`. Mock v2: `documentation/mockups/after-sales-p2/index.html` (carried over
from #2374; nothing in it touches complaints).

## Where the purchase date and kind are entered (and why not on a complaint line)

Crew's P2 brief says "on a complaint line". The owner's binding ruling of 12 Nov ~20:49 says otherwise:
"The after sales shouldn't affect how our current complaints work ... I want to not affect what's live now for
the complaint". P1 shipped under that ruling, and a guard test pins it
(`tests/test_after_sales_does_not_touch_complaints.py`).

So the line lives on the **service job** (P1, merged as #2365). The job page gets a **Products** card, and
each line holds:
- product: a catalogue product picker, searchable by code or name, with no free text;
- kind: prefilled from the rules, and can be changed;
- purchase date: dd/mm/yyyy;
- defect.

A **Warranty** card shows one answer per covered part, with the reason. No complaint table, field or screen
changes. Q0 below asks the owner to confirm this placement.

## Rules (ported from #163's engine and its tests; behaviour unchanged)

1. One answer per policy term for the line's kind. A water closet has 3 terms, so it gets 3 answers.
2. The policy used is the one in force on the **purchase date**, never today's. If no version covers that
   date, the answer is Unknown with the reason "No policy in force on dd/mm/yyyy".
3. Answers:
   - Covered: up to and including the expiry date.
   - Expired.
   - Defect not covered: the term lists defects and this defect is not one of them.
   - No term: the policy says nothing about this kind.
   - Unknown: the purchase date, the kind or the defect is missing, and the reason names which one. Unknown
     is never shown as "not covered".
4. Dates:
   - Cover runs from the purchase date to the same date N months or years later. Both dates count as covered; refusal starts the day after.
   - Months add with clamping: 31/01 + 1 month = 29/02.
   - Lifetime terms never expire.
5. Defects:
   - A term with no defect list covers every defect.
   - A term limited to certain defects, on a line with no defect, gives Unknown ("Defect not stated").
6. Kind:
   - The product code, category and name are matched against the kind rules (series, model list, category,
     code prefix).
   - If several rules match, the winner is decided by priority, then the more specific match, then the
     longer match, then the kind code.
   - A kind CS picks by hand is kept, and is never overwritten by the rules.
7. Configuration:
   - Policy versions may not overlap within a company.
   - Supersede closes the old version the day before the new one starts, in one save, and shows both
     versions' dates first.
   - A term is lifetime or a number of months, never both.
   - A kind that is used by a term, a rule or a job line cannot be deleted; it can be archived.
8. Clause 17 of the policy (residential only) is recorded but not enforced.
9. Policy v15 (31 kinds, 41 terms, 2 kind rules) is seeded from #163's seed and its source text. It is
   backdated to 01/01/2000 and open-ended, per the 2 Aug ruling recorded in that seed.

## Examples

These use the v15 terms as seeded. Customers, dates and codes are fake. Real masked rows from dev are
requested below.

| # | Job line (kind, purchase date, defect) | Answers on the job's Warranty card |
|---|---|---|
| 1 | Water Closet, 15/03/2020, Leakage | Ceramic body: **Covered**, lifetime ("crack line and leakage"). Flushing fittings: **Expired** 15/03/2025 (5 years). Seat cover soft close: **Expired** 15/03/2022 (2 years) |
| 2 | Water Closet, 02/05/2024, defect not entered | Ceramic body: **Unknown** ("Defect not stated", because that term covers only crack line and leakage). Flushing fittings: **Covered** to 02/05/2029. Seat cover: **Expired** 02/05/2026 |
| 3 | Stainless Steel 304 Kitchen Sink, 10/01/2010, Leakage | Rust resistant (25 years, rust only): **Defect not covered** ("This term covers Rust") |
| 4 | Automatic Water Booster Pump, purchase date not entered | Manufacturing defects and PC auto controller: **Unknown** ("Purchase date not entered") |
| 5 | Mirror Cabinet, 31/01/2024, Broken holder | Aluminium frame (10y): **Covered** to 31/01/2034. Hinges (25y): **Covered** to 31/01/2049. Mirror glass (2y): **Expired** 31/01/2026 |

Data request (crew-ask, masked): 5 dev complaints that have a product code and a filled "Within warranty"
text, with product code, product category and complaint date. The purpose is to replace these shapes with
real ones and to see which product categories reach which v15 kind.

## Edge cases

- The product's kind is missing, the rules don't reach it, and CS doesn't pick one: every answer is Unknown
  ("Kind not set").
- The purchase date is in the future: refused on save ("Purchase date cannot be after today").
- The same product is on two lines: allowed (two units). Each line gets its own answers.
- A policy is superseded after a job was checked: answers are computed when read, and the purchase date
  decides the version, so old purchases keep their old version's answer.
- An archived kind stays on existing lines and is not offered on new ones.
- A product with no kind rule: the line can still be saved with a kind picked by hand.

## Questions (each with a recommendation)

0. Where does the check live?
   - (a) on the service job (above, and mock v2);
   - (b) on the complaint line (crew's wording; this reverses the 12 Nov ruling);
   - (c) a separate warranty-check record.

   Recommendation: (a). It keeps complaints untouched as ruled, and puts one case in one place.
1. Who edits the policy, kinds and rules?
   - (a) admins only;
   - (b) admins, plus a warranty-manager permission that can be granted to a CS lead.

   Recommendation: (b). It is the same permission pair, just grantable.
2. Who sees the Warranty card and the list column?
   - (a) everyone who can view service jobs;
   - (b) only warranty-permission holders.

   Recommendation: (a). CS needs it on every job.
3. The 29 of 31 kinds with no product rule:
   - (a) the lane guesses rules from product categories;
   - (b) ops maps them on the Rules tab after the PR, with the tester.

   Recommendation: (b). A guessed mapping gives wrong answers with confidence.
4. `products.warranty_months` on main (a single months field per product, unused by the engine):
   - (a) leave it as it is;
   - (b) show it as a fallback when a product has no kind.

   Recommendation: (a). One source of truth (the policy). A per-product override is a later change only if
   ops asks.
