import { describe, expect, it } from 'vitest';
import { describePoBook, poOffset, type PoReceipt } from './poCover';

/**
 * S15: "if there is outstanding PO already then why should i buy" - the PO book offsets
 * the buy SUGGESTION (never the engine's netting), and the receipts travel with it.
 */

const receipt = (over: Partial<PoReceipt> = {}): PoReceipt => ({
  po_number: 'PO-2026/07-0002',
  status: 'active',
  expected_date: '2026-08-10',
  remaining: 504,
  ...over,
});

describe('poOffset', () => {
  it('a PO that covers the whole shortage leaves nothing to buy', () => {
    expect(poOffset(200, 504)).toEqual({ usePo: 200, buy: 0 });
  });

  it('a partial PO leaves the remainder as the buy', () => {
    expect(poOffset(200, 120)).toEqual({ usePo: 120, buy: 80 });
  });

  it('no PO leaves the buy untouched', () => {
    expect(poOffset(200, 0)).toEqual({ usePo: 0, buy: 200 });
  });

  it('never applies more PO than the shortage needs', () => {
    expect(poOffset(0, 504)).toEqual({ usePo: 0, buy: 0 });
  });
});

describe('describePoBook', () => {
  it('names each order with its quantity and promise date', () => {
    expect(describePoBook([receipt()])).toEqual([
      '504 still to come on PO-2026/07-0002, expected 2026-08-10.',
    ]);
  });

  it('an order with no promise date says so rather than inventing one', () => {
    expect(describePoBook([receipt({ expected_date: null })])).toEqual([
      '504 still to come on PO-2026/07-0002, no promised date.',
    ]);
  });
});
