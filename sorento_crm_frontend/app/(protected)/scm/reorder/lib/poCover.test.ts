import { describe, expect, it } from 'vitest';
import {
  describePoBook,
  type PoReceipt,
} from './poCover';

/**
 * S15: "if there is outstanding PO already then why should i buy" - since #828 the ENGINE
 * nets the open PO book, so what is left here is the receipt list the figure stands for
 * (`poOffset` is deleted, PLAN-reorder-one-formula.md).
 */

const receipt = (over: Partial<PoReceipt> = {}): PoReceipt => ({
  po_number: 'PO-2026/07-0002',
  status: 'active',
  expected_date: '2026-08-10',
  remaining: 504,
  ...over,
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
