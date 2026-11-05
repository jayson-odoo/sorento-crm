/**
 * STOCK-DEBT-SNAPSHOT AC-F6: `rowRemaining` and `reserveIneligibleReason`, moved verbatim from
 * `OrderInquiryDetail.tsx` (BLOCKER B1, AC-RS-23, N9). Same arithmetic, same words, so the OI
 * page and the snapshot drill can never disagree about which row may be requested.
 */
import { describe, expect, it } from 'vitest';
import { reserveIneligibleReason, rowRemaining } from './reserveEligibility';

function row(over: Record<string, unknown> = {}) {
  return {
    id: 'row-1',
    item_code: 'SRTWT904-NL',
    qty: '100',
    linked_qty: '0',
    reserved_qty: '0',
    bundled_qty: '0',
    verb: 'ORDER',
    state: 'raised',
    reserve_state: null,
    ...over,
  } as never;
}

describe('rowRemaining', () => {
  it('is qty less linked, reserved and bundled', () => {
    expect(
      rowRemaining(row({ qty: '100', linked_qty: '10', reserved_qty: '20', bundled_qty: '5' })),
    ).toBe(65);
  });

  it('treats absent quantities as 0', () => {
    expect(
      rowRemaining(
        row({ qty: '30', linked_qty: undefined, reserved_qty: undefined, bundled_qty: undefined }),
      ),
    ).toBe(30);
  });

  it('can go negative when the row is over-covered (callers floor it)', () => {
    expect(rowRemaining(row({ qty: '10', linked_qty: '12' }))).toBe(-2);
  });
});

describe('reserveIneligibleReason', () => {
  it('is null for a raised ORDER row with something left', () => {
    expect(reserveIneligibleReason(row())).toBeNull();
  });

  it('accepts ORDER_BACK and partly_linked', () => {
    expect(reserveIneligibleReason(row({ verb: 'ORDER_BACK', state: 'partly_linked' }))).toBeNull();
  });

  // OI-RESERVE-ANY-ROW (owner, 5 Nov 2026): any row that is not Done, whatever its verb.
  it.each(['DELAY', 'ADVANCE', 'RESERVE_AND_ORDER', 'CHANGE_SO'])('accepts a not-Done %s row', (verb) => {
    expect(reserveIneligibleReason(row({ verb }))).toBeNull();
  });

  it('refuses a Done row whatever its verb', () => {
    expect(reserveIneligibleReason(row({ verb: 'DELAY', state: 'actioned' }))).toBe(
      'SRTWT904-NL: not open for a reserve request',
    );
  });

  it('refuses a used row whatever its verb', () => {
    expect(reserveIneligibleReason(row({ verb: 'DELAY', redirected_to_pool: true }))).toBe(
      "SRTWT904-NL: a used row, request on its line's live row",
    );
  });

  // OI-RESERVE-RECEIVED (#1708) made `placed` requestable; `actioned` is still refused.
  it('refuses a row that is not raised, partly linked or placed', () => {
    expect(reserveIneligibleReason(row({ state: 'actioned' }))).toBe(
      'SRTWT904-NL: not open for a reserve request',
    );
  });

  it('refuses a row with nothing left to request', () => {
    expect(reserveIneligibleReason(row({ qty: '30', linked_qty: '30' }))).toBe(
      'SRTWT904-NL: has nothing left to request',
    );
  });

  it('refuses a row that already has an open request', () => {
    expect(reserveIneligibleReason(row({ reserve_state: 'requested' }))).toBe(
      'SRTWT904-NL: already has an open reserve request',
    );
  });

  it('falls back to "This row" when the item code is missing', () => {
    expect(reserveIneligibleReason(row({ item_code: null, state: 'actioned' }))).toBe(
      'This row: not open for a reserve request',
    );
  });

  it('checks the state before the quantity', () => {
    expect(reserveIneligibleReason(row({ state: 'actioned', qty: '1', linked_qty: '1' }))).toMatch(
      /not open for a reserve request/,
    );
  });
});
