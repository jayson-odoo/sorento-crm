import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import type { TownShop, TownSnapshot } from '@/types/town.types';
import { EASE, EASE_STANDARD, newSales, trapezoid } from './townMotion';

const shop = (key: string, docs: number, amount?: string): TownShop => ({
  key, kind: 'shop', account_label: null, today_docs: docs, today_amount: amount,
});

function snapshot(shops: TownShop[], amount?: string, extra: Partial<TownSnapshot> = {}): TownSnapshot {
  return {
    schema: 1, company_id: 'c', day: '2026-01-05', as_of: '2026-01-05T10:00:00+08:00', data_as_of: null, phase: 'day',
    today: { amount, invoice_count: shops.reduce((sum, s) => sum + s.today_docs, 0), credit_note_count: 0, customer_count: 1, dealer_customer_count: 1 },
    shops, warehouses: [], reorder: { below_count: 0, set_count: 0 },
    approvals: { total: 0, purchase_requests: 0, quotation_documents: 0 },
    ...extra,
  };
}

describe('newSales', () => {
  const before = snapshot([shop('a', 1, '100.00'), shop('b', 0), shop('c', 2, '50.00')], '150.00');

  it('finds nothing on the first load, or when the same snapshot comes back', () => {
    expect(newSales(null, before)).toBeNull();
    expect(newSales(undefined, before)).toBeNull();
    expect(newSales(before, before)).toBeNull();
  });

  it('finds nothing when no shop has more invoices than before', () => {
    expect(newSales(before, snapshot([shop('a', 1, '100.00'), shop('b', 0), shop('c', 2, '50.00')], '150.00'))).toBeNull();
    // a shop with fewer invoices (a credit note) is not a sale
    expect(newSales(before, snapshot([shop('a', 0), shop('b', 0), shop('c', 2, '50.00')], '50.00'))).toBeNull();
  });

  it('gives one entry per shop with an increase, busiest first, and the summed amount', () => {
    const after = snapshot([shop('a', 2, '340.00'), shop('b', 3, '900.00'), shop('c', 2, '50.00')], '1290.00');
    const beat = newSales(before, after);
    expect(beat).toEqual({
      shops: [
        { key: 'b', docs: 3, amount: 900 },
        { key: 'a', docs: 1, amount: 240 },
      ],
      invoices: 4,
      amount: 1140,
    });
  });

  it('counts a shop that was not in the last snapshot as new', () => {
    const beat = newSales(before, snapshot([...before.shops, shop('d', 1, '25.00')], '175.00'));
    expect(beat?.shops).toEqual([{ key: 'd', docs: 1, amount: 25 }]);
    expect(beat?.amount).toBe(25);
  });

  it('carries invoices only for a viewer without amounts (redacted or wallboard)', () => {
    const quiet = snapshot([shop('s1', 1), shop('s2', 0)]);
    const beat = newSales(quiet, snapshot([shop('s1', 2), shop('s2', 1)]));
    expect(beat).toEqual({
      shops: [
        { key: 's1', docs: 1, amount: null },
        { key: 's2', docs: 1, amount: null },
      ],
      invoices: 2,
      amount: null,
    });
  });

  it('hides the sum when the board total is hidden, even if a shop amount is present', () => {
    const beat = newSales(snapshot([shop('a', 1, '10.00')]), snapshot([shop('a', 2, '30.00')]));
    expect(beat?.invoices).toBe(1);
    expect(beat?.amount).toBeNull();
  });

  it('plays nothing between two views with no shop key in common (personal ids against Wallboard keys)', () => {
    const wallboard = snapshot([shop('s0a1b2c3d4e5f', 2), shop('s9f8e7d6c5b4a', 3)]);
    expect(newSales(before, wallboard)).toBeNull();
    expect(newSales(wallboard, before)).toBeNull();
  });

  it('plays nothing across a new day or another company', () => {
    const after = snapshot([shop('a', 5, '999.00')], '999.00');
    expect(newSales(before, { ...after, day: '2026-01-06' })).toBeNull();
    expect(newSales(before, { ...after, company_id: 'other' })).toBeNull();
  });
});

describe('motion vocabulary', () => {
  it('solves the same curve as the --ease-standard token in css/config.reui.css', () => {
    const css = fs.readFileSync(path.resolve(__dirname, '../../../../css/config.reui.css'), 'utf8');
    const tokens = [...css.matchAll(/--ease-standard:\s*cubic-bezier\(([^)]*)\)/g)].map((m) => m[1].split(',').map(Number));
    expect(tokens.length).toBeGreaterThan(0);
    tokens.forEach((numbers) => expect(numbers).toEqual([0.2, 0, 0, 1]));
    expect([...EASE_STANDARD]).toEqual([0.2, 0, 0, 1]);
  });

  it('eases on --ease-standard: 0 to 1, monotonic, fast out of the start', () => {
    expect(EASE(0)).toBe(0);
    expect(EASE(1)).toBe(1);
    let prev = 0;
    for (let x = 0.05; x < 1; x += 0.05) {
      expect(EASE(x)).toBeGreaterThanOrEqual(prev);
      prev = EASE(x);
    }
    expect(EASE(0.5)).toBeGreaterThan(0.8);
  });

  it('moves a body with mass from rest to rest over the whole distance', () => {
    for (const [L, v, a] of [[100, 5, 2], [2, 5, 2]]) {
      const p = trapezoid(L, v, a);
      expect(p.at(0)).toBe(0);
      expect(p.at(p.T)).toBeCloseTo(L);
      expect(p.vel(0)).toBe(0);
      expect(p.vel(p.T)).toBe(0);
      expect(Math.max(...Array.from({ length: 50 }, (_, i) => p.vel((i / 50) * p.T)))).toBeLessThanOrEqual(v + 1e-9);
    }
  });
});
