import { describe, expect, it } from 'vitest';

import { allocationLocation } from './allocationLocation';

describe('allocationLocation', () => {
  it('names the warehouse when we hold one', () => {
    expect(
      allocationLocation({
        warehouse: { id: 'w1', warehouse_code: 'BRW-IB', warehouse_name: 'Brickworks IB' },
        location_code: 'BRW-IB',
      }),
    ).toBe('BRW-IB');
  });

  it('falls back to the code the book spelled when we hold no such location', () => {
    expect(
      allocationLocation({ warehouse: undefined, location_code: 'RESERVE' }),
    ).toBe('RESERVE');
  });

  it('shows a dash only when the line stated no location at all', () => {
    expect(allocationLocation({ warehouse: undefined, location_code: null })).toBe('-');
  });
});
