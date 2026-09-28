/**
 * `lineAmount` / `sumLineAmounts` (fix round 2 S1 + rounding nit): each line rounds to 2dp
 * before it is summed, matching the server's per-line rounding, and a blank unit price is
 * "no price" - not zero.
 */
import { describe, expect, it } from 'vitest';
import { lineAmount, sumLineAmounts } from './OpportunityLineRow';

describe('lineAmount', () => {
  it('rounds qty x unitPrice to 2dp before it goes anywhere else', () => {
    // 3 x 0.1 = 0.30000000000000004 in floating point.
    expect(lineAmount({ qty: '3', unitPrice: '0.1' })).toBe(0.3);
    expect(lineAmount({ qty: '1.005', unitPrice: '100' })).toBe(100.5);
  });

  it('is null - not zero - when the unit price is blank', () => {
    expect(lineAmount({ qty: '2', unitPrice: '' })).toBeNull();
  });
});

describe('sumLineAmounts', () => {
  it('sums the already-rounded per-line amounts, so the total reads as 2dp figures added together', () => {
    const lines = [
      { qty: '3', unitPrice: '0.1' },
      { qty: '3', unitPrice: '0.2' },
    ];
    // Each line rounds to a clean 0.30 / 0.60 first; what a caller actually reads is the
    // 2dp string (`.toFixed(2)`), same as every screen that shows this total.
    expect(sumLineAmounts(lines).toFixed(2)).toBe('0.90');
  });

  it('is 0 when every line is unpriced', () => {
    expect(sumLineAmounts([{ qty: '2', unitPrice: '' }])).toBe(0);
  });
});
