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

export interface ReserveRowRequestAnchorCandidate {
  id: string;
  ordinal: number;
  /** This ROW's own `qty_reserved` on that request - already known to be non-null
   * (answered), the caller's own filter. */
  rowQtyReserved: string | null;
}

/**
 * 6e.4 (reviewer B3): which answered request row anchors Amend (and History) for a
 * line - the LATEST answered one by ordinal, the same row the server's own
 * `commit_request` resolves an `amendments` entry to. Its own `qty_reserved` is the
 * amend prefill, so the number CS edits is the number the server amends, even when an
 * earlier request still holds stock on the same line.
 */
export function resolveReserveRowRequestAnchor(
  answeredRequests: ReserveRowRequestAnchorCandidate[],
): string | null {
  const byOrdinalDesc = [...answeredRequests].sort((a, b) => b.ordinal - a.ordinal);
  return byOrdinalDesc[0]?.id ?? null;
}

// `reserveRequestCompletes` (O2/O3, fix round 4 nits) is retired round 4 - see
// `orderInquiryReserve.test.ts`'s own note.

/**
 * N1 (fix round 4 nit, carried into round 4): a `SearchableSelect` option's own
 * `label` carries the available-qty suffix in production (`useReserveRowOptions.ts`:
 * `${location}  available ${qty}`, two spaces) - reading it straight would flash
 * "Reserve 20 @ DC1  available 20" on the staged chip. The BARE code is everything
 * before that double space (absent in a fixture that never carries the suffix, where
 * this is a no-op).
 */
export function bareLocationCode(label: string): string {
  return label.split('  ')[0];
}
