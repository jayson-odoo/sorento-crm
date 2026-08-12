import { describe, expect, it } from 'vitest';
import { describePurchaseTrend, type ProductPurchaseTrend } from './purchaseTrend';

const trend = (over: Partial<ProductPurchaseTrend> = {}): ProductPurchaseTrend => ({
  recent_qty: 400,
  previous_qty: 1200,
  lines: [
    {
      supplier_code: 'S-1', supplier_name: 'Acme Supplies', po_number: 'PO-1',
      order_date: '2026-07-01', qty: 100, unit_cost: 72, currency: 'USD',
    },
  ],
  ...over,
});

describe('describePurchaseTrend', () => {
  it('states both windows with their numbers, never a bare percentage', () => {
    expect(describePurchaseTrend(trend(), 3)).toBe(
      'Purchased 400 in the last 3 months, 1,200 in the 3 months before.',
    );
  });

  it('says never purchased when the product has no purchase history at all', () => {
    expect(
      describePurchaseTrend(trend({ recent_qty: 0, previous_qty: 0, lines: [] }), 3),
    ).toBe('Never purchased in the imported history.');
  });

  it('says never purchased for an undefined entry (the product carries no opinion)', () => {
    expect(describePurchaseTrend(undefined, 3)).toBe('Never purchased in the imported history.');
  });

  it('still states the trend when only the earlier window has activity', () => {
    expect(
      describePurchaseTrend(trend({ recent_qty: 0, previous_qty: 500 }), 3),
    ).toBe('Purchased 0 in the last 3 months, 500 in the 3 months before.');
  });
});
