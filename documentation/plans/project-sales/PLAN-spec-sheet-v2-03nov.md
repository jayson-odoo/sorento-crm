# PLAN: Spec sheet tab v2, saved spec sheets list + PDF-style viewer (SPEC-SHEET-V2)

**Status:** Plan stage: behaviour card in progress (owner feedback 3 Nov 11:35 on PRJQ-2026-0007).
Track: L (new table migration, new routes). Builds on #2103 (`PLAN-ps-spec-sheet-02nov.md`).
UAC: `spec-sheet-v2-03nov-acceptance-criteria.md` (after the mock is approved).

## Owner feedback (3 Nov ~11:35, verbatim)

"the selection of 4 things is very not compliant with the system design. The spec sheet needs a
table listing the spec sheets created; when I click Create spec sheet I can select the revision.
Now the revision must be signed back by the customer, right? Actually when we send to the customer
we already send the catalogue, so we shouldn't need to wait until the customer signs back. When I
view the spec sheet it should be a natural PDF scrolling motion, with the ability to further edit /
amend using the designer we have."

## Process

1. Behaviour card (crew-ask): rules, real examples, edge cases, questions.
2. Lavish mock (static HTML, app design system) as crew-ask; build only after owner OK.
3. Red-first tests, coder, reviewer + security review (new table), browser pass, hand test.
