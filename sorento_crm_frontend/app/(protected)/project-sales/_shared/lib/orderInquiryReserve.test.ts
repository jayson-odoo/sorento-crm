/**
 * S1 (reviewer round, `PLAN-oi-request-cs-reserve.md` AC-RS-19): the Cancel control on
 * an open reserve request must never be offered to someone the server will 403 for
 * pressing it - `cancel_request`'s own rule is "the requester who raised it, or anyone
 * holding the reserve permission".
 */
import { describe, expect, it } from 'vitest';
import { canCancelReserveRequest } from './orderInquiryReserve';

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
