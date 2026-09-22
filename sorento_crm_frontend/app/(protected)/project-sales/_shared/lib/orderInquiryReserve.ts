/**
 * Pure predicates for the "request CS to reserve" feature that are worth pinning
 * without mounting `OrderInquiryDetail` or `ReserveRowDialog` (`PLAN-oi-request-cs-
 * reserve.md`).
 */

/**
 * S1 (reviewer round, `PLAN-oi-request-cs-reserve.md` section 3.2, AC-RS-19): who may
 * cancel an OPEN reserve request - CS (the `RESERVE` permission), or the very person
 * who raised it. `ACKNOWLEDGE` alone used to be offered the Cancel control too (any
 * purchasing user who can raise a request could see the button on ANY open request),
 * and the server's own ownership check (`cancel_request`: "the requester who raised
 * it, or anyone holding the reserve permission") 403s a colleague who presses it - the
 * button ran the whole deferred-action countdown before failing. This mirrors the
 * server's own rule exactly, so the button never offers what the server will refuse.
 */
export function canCancelReserveRequest(
  currentUserId: string | null | undefined,
  requestedBy: string | null | undefined,
  canReserve: boolean,
): boolean {
  if (canReserve) return true;
  if (!currentUserId || !requestedBy) return false;
  return currentUserId === requestedBy;
}
