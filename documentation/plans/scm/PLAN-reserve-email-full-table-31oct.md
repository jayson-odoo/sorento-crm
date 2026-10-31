# PLAN: reserve request/reserved emails - full per-line table, scoped link, per-CS question

Status: Build. Owner approved mockup v4 on 31 Oct with OI NO first. Track: size M per the crew brief (tester, coder, reviewer), one guarded template-data migration, no schema change, no RBAC change.

crew-lane: RESERVE-EMAIL-FULL-TABLE

Source: stakeholder feedback 30 Oct (purchasing/stock, via owner 31 Oct). Behaviour card:
`reserve-email-full-table-behaviour-card.md` (alongside).

UAC: `reserve-email-full-table-acceptance-criteria.md`.

## Slices

1. Red tests from the UAC (tester), committed alone as `test(red):`.
2. Backend: one flat line list in the reserve context, STATUS and REASON, split by raiser, no more split
   per request, immediate send merged per OI and requester, guarded template migration, `inquiry_no` filter.
3. Frontend: `inquiry_no` on the OI list (URL round trip, removable filter, state All on arrival).
4. Kill test, reviewer, guide `documentation/user-guides/supply-chain/order-inquiry-reserve-email.md`,
   hand-test script.
