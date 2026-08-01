import { describe, it, expect } from 'vitest';
import { pickingLineSchema } from './grn-schema';

// S17-1a: AutoCount ships fractional goods-received quantities ("2.5"). The GRN
// line form must accept decimals, not just integers, or a fractional receipt is
// silently rejected at the client before it ever reaches the Decimal-widened
// backend column.
describe('pickingLineSchema quantity (S17 Decimal)', () => {
  const base = { product_id: 'p1', source_warehouse_id: 'w1' };

  it('accepts a fractional quantity_picked', () => {
    const parsed = pickingLineSchema.safeParse({
      ...base,
      quantity_expected: '2.5',
      quantity_picked: '2.5',
    });
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      expect(parsed.data.quantity_picked).toBe(2.5);
      expect(parsed.data.quantity_expected).toBe(2.5);
    }
  });

  it('still accepts whole numbers', () => {
    const parsed = pickingLineSchema.safeParse({
      ...base,
      quantity_expected: '4',
      quantity_picked: '4',
    });
    expect(parsed.success).toBe(true);
    if (parsed.success) expect(parsed.data.quantity_picked).toBe(4);
  });

  it('rejects a negative quantity', () => {
    const parsed = pickingLineSchema.safeParse({
      ...base,
      quantity_expected: '1',
      quantity_picked: '-1',
    });
    expect(parsed.success).toBe(false);
  });
});
