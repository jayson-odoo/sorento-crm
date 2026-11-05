# PLAN: OI reserve on any row that is not Done (OI-RESERVE-ANY-ROW)

Status: Plan (small fix track: no migration, no auth/RBAC change)

## Ruling (owner, 5 Nov 2026 ~10:25 MYT, verbatim)

"obviously a delay row is reservable ... any row that is not Done are reservable ah, doesn't
matter the Delay or Advance or not, isn't that the current behaviour already?"

## Today (main 2adb19b7)

- Server refuses a reserve REQUEST on anything but ORDER / ORDER_BACK rows
  (`order_inquiry_reserve_service.py` `_REQUESTABLE_VERBS`, `create_request`).
- Frontend mirrors it (`reserveEligibility.ts` `reserveIneligibleReason`).
- The OI lines grid counts Reserve requested / Reserved from buy rows only, so a request on a
  DELAY row shows in the State pill but "-" in the columns.
- The reserve STEP has no verb check.

Plan body and UAC follow in the next commit.
