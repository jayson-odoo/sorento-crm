/**
 * Pure-function coverage for the line amount helpers (nit: round each line to 2dp before
 * summing, or the total can drift a cent from what the individual lines themselves show).
 */
import { describe, expect, it } from 'vitest';
import { lineDraftAmount, sumLineDraftAmounts, type LineDraft } from './PortalOpportunityLineRow';

function line(qty: string, unitPrice: string): LineDraft {
  return { key: 'k', productId: 'p1', productLabel: 'P1', qty, unitPrice };
}

describe('lineDraftAmount', () => {
  it('returns null when qty or unit price is blank', () => {
    expect(lineDraftAmount(line('', '10'))).toBeNull();
    expect(lineDraftAmount(line('2', ''))).toBeNull();
  });

  it('rounds to 2dp', () => {
    expect(lineDraftAmount(line('0.1', '0.01'))).toBe(0);
    expect(lineDraftAmount(line('0.1', '0.04'))).toBe(0);
  });
});

describe('sumLineDraftAmounts', () => {
  it('nit: sums the ROUNDED per-line amounts - two lines that each round to nothing add to nothing', () => {
    // 0.1 * 0.01 = 0.001 and 0.1 * 0.04 = 0.004: each line, on its own, rounds to RM 0.00.
    // Summing the raw (unrounded) products first gives 0.005, which itself rounds up to
    // 0.01 - a total the two visible RM 0.00 lines never add up to.
    const lines = [line('0.1', '0.01'), line('0.1', '0.04')];
    expect(sumLineDraftAmounts(lines).toFixed(2)).toBe('0.00');
  });
});
