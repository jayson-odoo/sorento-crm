/**
 * AC-S11.2/AC-S11.4 (round 2, reorder-feedback-9sep): the row's line cost is Buy qty x
 * LAST PRICE, in the purchase's own currency, when "Use last price" is selected and a
 * last price is on file; otherwise Buy qty x the chosen SUPPLIER's own cost, in the
 * supplier's own currency; with neither, no figure at all.
 *
 * Pinned as a pure function so `PlanRowPanel` reads it rather than re-deriving the
 * base-currency `m8CashImpact` figure the row used to show under this label.
 */
import { describe, expect, it } from 'vitest';
import { lineCost } from './lineCost';

describe('lineCost (AC-S11.2)', () => {
  it('is Buy qty x last price, in the last purchase currency, on "use_last"', () => {
    const result = lineCost({
      buyQty: 462,
      priceMode: 'use_last',
      last: { unit_cost: 48, currency: 'CNY' },
      supplier: { unit_cost: 121.8, currency: 'MYR' },
    });
    expect(result).toEqual({ amount: 22176, currency: 'CNY', basis: 'last' });
  });

  it('is Buy qty x the chosen supplier cost, in the supplier currency, on "ask_new"', () => {
    const result = lineCost({
      buyQty: 10,
      priceMode: 'ask_new',
      last: { unit_cost: 48, currency: 'CNY' },
      supplier: { unit_cost: 3.5, currency: 'USD' },
    });
    expect(result).toEqual({ amount: 35, currency: 'USD', basis: 'supplier' });
  });

  it('falls back to the supplier cost on "use_last" when there is no last price on file', () => {
    const result = lineCost({
      buyQty: 10,
      priceMode: 'use_last',
      last: null,
      supplier: { unit_cost: 3.5, currency: 'USD' },
    });
    expect(result).toEqual({ amount: 35, currency: 'USD', basis: 'supplier' });
  });

  it('is null with neither a last price nor a supplier cost', () => {
    const result = lineCost({
      buyQty: 10,
      priceMode: 'ask_new',
      last: null,
      supplier: { unit_cost: null, currency: null },
    });
    expect(result).toBeNull();
  });
});
