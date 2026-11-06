# PLAN: Stock Debt PO link retryable after an AutoCount refusal (lane STOCKDEBT-LINK-IDEM-KEY)

Status: Review (reviewer READY at 46ed548b; should-fix 1 and nits 2, 3, 5, 6 taken). Track: small fix (no migration, no auth/RBAC change, no new ingest surface).
Feature switch "AutoCount links from Stock Debt" stays OFF.

## Facts (main at 61e9d217)

- `stock_debt_po_link_service.py:335-343` `_intent_key` is already `sha256(path | every body field
  sorted | rowQty)`: a corrected body already gets a new key, and
  `tests/scm/test_stock_debt_po_link.py` `test_the_same_intent_sends_the_same_idempotency_key`
  already asserts it. IDEMPOTENCY_CONFLICT cannot happen on this service.
- The dead end (AC-E2E-DB3 B3): the body is CRM keys and qty only. A refusal fixed outside the body
  (blank PurchaseAgent, fixed in SS #225; any AutoCount-side data fix) is retried with the identical
  body, so the same key, and the Shared Service replays the stored refusal forever.
- Key builders: link, unlink, relink use `_intent_key` (all three changed). relocate and resume send
  no Idempotency-Key, so they are never stuck (unchanged). No SPO write exists on main.

## Fix

`app/services/autocount_idempotency.py` (shareable with AC-QTSO-CRM):
- `send_with_attempts(store, base_key, send)`: the key is `attempt_key(base, n)`; attempt 0 is the
  base key unchanged.
- Only a definite refusal (`outcome == "refused"`, errorCode not `IDEMPOTENCY_*`) moves n on, kept in
  Redis per intent key for 30 days. A timeout, `pending_verification`, `needs_attention`,
  `vendor_error` or a key still in flight keeps the key, so a retry replays and never splits twice.
- Redis unreachable: attempt 0 (the old key), the write still goes.

## Open

- Crew ask on the PR: the alternative cure is SS not replaying stored `refused` answers (one place
  for PO links and QT/SO). If crew picks that, this lane's change is still harmless.
