/**
 * S1 (reviewer round, `PLAN-oi-request-cs-reserve.md` AC-RS-19): the Cancel control on
 * an open reserve request must never be offered to someone the server will 403 for
 * pressing it - `cancel_request`'s own rule is "the requester who raised it, or anyone
 * holding the reserve permission".
 */
import { describe, expect, it } from 'vitest';
import {
  canCancelReserveRequest,
  reserveRequestCompletes,
  resolveReserveRowRequestAnchor,
} from './orderInquiryReserve';

describe('canCancelReserveRequest', () => {
  it('a CS holder (canReserve) may cancel any open request, whoever raised it', () => {
    expect(canCancelReserveRequest('user-a', 'user-b', true)).toBe(true);
    expect(canCancelReserveRequest('user-a', null, true)).toBe(true);
  });

  it('the requester may cancel their own request without the reserve permission', () => {
    expect(canCancelReserveRequest('user-a', 'user-a', false)).toBe(true);
  });

  it('an ACKNOWLEDGE-only colleague may NOT cancel someone elses request - the server 403s this', () => {
    expect(canCancelReserveRequest('user-a', 'user-b', false)).toBe(false);
  });

  it('answers false with no current user or no requester on record, never a silent true', () => {
    expect(canCancelReserveRequest(null, 'user-b', false)).toBe(false);
    expect(canCancelReserveRequest('user-a', null, false)).toBe(false);
    expect(canCancelReserveRequest(undefined, undefined, false)).toBe(false);
  });
});

describe('resolveReserveRowRequestAnchor', () => {
  it('prefers the highest-ordinal request that still holds a link (qty_reserved > 0)', () => {
    expect(
      resolveReserveRowRequestAnchor([
        { id: 'rr-1', ordinal: 1, rowQtyReserved: '50' },
        { id: 'rr-2', ordinal: 2, rowQtyReserved: '0' },
      ]),
    ).toBe('rr-1');
  });

  it('falls back to any answered request when NONE still holds a link', () => {
    expect(
      resolveReserveRowRequestAnchor([
        { id: 'rr-1', ordinal: 1, rowQtyReserved: '0' },
        { id: 'rr-2', ordinal: 2, rowQtyReserved: '0' },
      ]),
    ).toBe('rr-2');
  });

  it('answers null with nothing answered yet', () => {
    expect(resolveReserveRowRequestAnchor([])).toBeNull();
  });
});

/**
 * O2/O3 (fix round 4 nits, `oi-request-cs-reserve-acceptance-criteria.md`). Extracted
 * from `OrderInquiryDetail.tsx`'s own inline `onReserve` handler specifically so
 * these two edges are unit-testable directly - reaching them through the full
 * rendered dialog is not really possible (a row's own `openRequest` and the request
 * this function reads are derived off the SAME query, so they cannot legitimately
 * disagree inside one React render the way a manufactured `request: undefined` or a
 * stale-cache race would need).
 */
describe('reserveRequestCompletes', () => {
  const rows = [
    { row_id: 'row-a', qty_reserved: null },
    { row_id: 'row-b', qty_reserved: null },
    { row_id: 'row-c', qty_reserved: '8' },
  ];

  it('true once every OTHER row already carries a non-null qty_reserved', () => {
    expect(
      reserveRequestCompletes({ rows: [{ row_id: 'row-a', qty_reserved: null }, { row_id: 'row-b', qty_reserved: '5' }] }, 'row-a'),
    ).toBe(true);
  });

  it('false while another row is still open, and not in alreadyConfirmedRowIds', () => {
    expect(reserveRequestCompletes({ rows }, 'row-a')).toBe(false);
  });

  it('O2: false when the request itself is missing from the cache - never a vacuous true off nothing to check', () => {
    expect(reserveRequestCompletes(undefined, 'row-a')).toBe(false);
    expect(reserveRequestCompletes(null, 'row-a')).toBe(false);
  });

  it('O3: a row named in alreadyConfirmedRowIds counts as answered even while its own qty_reserved still reads null', () => {
    expect(reserveRequestCompletes({ rows }, 'row-a', ['row-b'])).toBe(true);
  });

  it('O3: alreadyConfirmedRowIds alone is not enough - every row must be covered by one path or the other', () => {
    expect(reserveRequestCompletes({ rows }, 'row-a', [])).toBe(false);
  });
});
