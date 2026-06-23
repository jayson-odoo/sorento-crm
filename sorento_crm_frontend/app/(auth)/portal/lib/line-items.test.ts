import { describe, it, expect } from 'vitest';
import { cleanLineItems, computeLineTotal } from './line-items';

describe('computeLineTotal', () => {
  it('multiplies quantity by unit price', () => {
    expect(computeLineTotal('3', '10')).toBe('30.00');
    expect(computeLineTotal('2', '12.5')).toBe('25.00');
  });

  it('returns empty string when either side is blank or non-numeric', () => {
    expect(computeLineTotal('', '10')).toBe('');
    expect(computeLineTotal('3', '')).toBe('');
    expect(computeLineTotal('abc', '10')).toBe('');
    expect(computeLineTotal(undefined, undefined)).toBe('');
  });
});

describe('cleanLineItems', () => {
  it('persists the computed total when the Total box is empty', () => {
    const out = cleanLineItems([
      { item_code: 'A1', quantity: '3', unit_price: '10', total: '', remark: '' },
    ]);
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({
      item_code: 'A1',
      quantity: '3',
      unit_price: '10',
      total: '30.00',
      remark: null,
    });
  });

  it('respects an explicitly typed Total over the computed value', () => {
    const out = cleanLineItems([
      { item_code: 'A1', quantity: '3', unit_price: '10', total: '99.99' },
    ]);
    expect(out[0].total).toBe('99.99');
  });

  it('keeps a priced-only line (no item code, no quantity, no remark)', () => {
    const out = cleanLineItems([
      { item_code: '', quantity: '', unit_price: '50', total: '' },
    ]);
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({
      item_code: null,
      quantity: null,
      unit_price: '50',
      total: null,
    });
  });

  it('keeps a total-only line', () => {
    const out = cleanLineItems([{ total: '120' }]);
    expect(out).toHaveLength(1);
    expect(out[0].total).toBe('120');
  });

  it('drops an entirely empty line', () => {
    const out = cleanLineItems([
      { item_code: '', quantity: '', unit_price: '', total: '', remark: '' },
    ]);
    expect(out).toHaveLength(0);
  });

  it('keeps a remark-only line', () => {
    const out = cleanLineItems([{ remark: 'special handling' }]);
    expect(out).toHaveLength(1);
    expect(out[0].remark).toBe('special handling');
  });
});
