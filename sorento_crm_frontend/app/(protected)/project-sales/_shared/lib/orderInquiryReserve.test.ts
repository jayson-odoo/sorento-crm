/**
 * S1 (reviewer round, `PLAN-oi-request-cs-reserve.md` AC-RS-19): the Cancel control on
 * an open reserve request must never be offered to someone the server will 403 for
 * pressing it - `cancel_request`'s own rule is "the requester who raised it, or anyone
 * holding the reserve permission".
 */
import { describe, expect, it } from 'vitest';
import { canCancelReserveRequest, resolveReserveRowRequestAnchor } from './orderInquiryReserve';

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

// `reserveRequestCompletes` (O2/O3, fix round 4 nits) is retired round 4
// (`PLAN-oi-request-cs-reserve.md` 6e.1/6e.2): whether a commit completes its
// request is now server truth alone (`commit_request`'s own `reserve.open_row_count`),
// never a client-side guess built for a per-row confirm's own toast wording - the
// staged-map CTA posts ONE batched commit and reads the response, it never asks this
// question of the cache mid-flow.
