# PLAN: price tag upgrade items on combos + one tag per product family with variant icons

Status: Plan, Waiting on owner (card fully answered 09/11/2026 ~12:00; mock v1 `pricetag-upgrade-variants-mock.html` filed for approval). Track: decided after answers
(expected full: a spec-registry change for numeric value icons, payload + designer changes; no migration
expected under the recommended answers).

Lane: PRICETAG-UPGRADE-VARIANTS. Behaviour card: `CARD-pricetag-upgrade-variants-09nov.md` (rules U1-U9, F1-F8).

## Next steps

1. Owner answers Q1-Q5 (crew-ask on the PR).
2. Mock in the Tag Template designer (existing components): Accessories box "Lists: Upgrades" with an upgrade
   card (Top-up, SP with upgrade, Feature icons element); feature icons layer "Reads from: All variants";
   numeric spec values carrying icons on Master Data > Product Specifications.
3. UAC file `pricetag-upgrade-variants-acceptance-criteria.md`, then tests red first, build, render-accuracy
   checks (canvas = preview = print through the one layout function), reviewer, browser pass.
