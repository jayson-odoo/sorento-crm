/**
 * Money renders in the currency it is actually in.
 *
 * `fmtMoney` hard-codes RM, which is right for the figures that ARE ringgit: valuations,
 * the budget, cash impact. It is wrong for a supplier's price, and the purchase-order book
 * is 8438 lines USD against 4186 MYR - so on most prices "RM 45" was a wrong number
 * printed as a fact, next to a purchase order that says USD.
 */
import { describe, expect, it } from 'vitest';

import {
  BASE_CURRENCY,
  EM_DASH,
  fmtDateTime,
  fmtMoney,
  fmtMoneyIn,
  fmtSupplierCost,
  fmtTrimmedDecimal,
} from './format';

describe('fmtSupplierCost', () => {
  it('names a foreign currency instead of claiming ringgit', () => {
    expect(fmtSupplierCost(45, 'USD')).toBe('USD 45.00');
  });

  it('renders the base currency the way the rest of the dashboard does', () => {
    // Same glyph as `fmtMoney`, so a ringgit price does not suddenly read differently
    // just because it came down a different field.
    expect(fmtSupplierCost(190, BASE_CURRENCY)).toBe('RM 190.00');
  });

  it('reads a price with no currency as the base currency', () => {
    // Rows predating the book having more than one currency carry no code, and that
    // figure already meant ringgit.
    expect(fmtSupplierCost(190, null)).toBe('RM 190.00');
  });

  it('shows a recorded zero as a price rather than as nothing', () => {
    // Free is an answer. Blanking it would make it indistinguishable from never-bought.
    expect(fmtSupplierCost(0, 'USD')).toBe('USD 0.00');
  });

  it('shows an em dash when there is no price at all', () => {
    expect(fmtSupplierCost(null, 'USD')).toBe(EM_DASH);
    expect(fmtSupplierCost(undefined, 'USD')).toBe(EM_DASH);
  });

  it('keeps the cents, because a unit price of 4.35 is not 4', () => {
    expect(fmtSupplierCost(4.35, 'USD')).toBe('USD 4.35');
  });

  it('separates thousands so a five-figure price is readable at a glance', () => {
    expect(fmtSupplierCost(12345.5, 'USD')).toBe('USD 12,345.50');
  });
});

describe('fmtMoney', () => {
  it('still renders base-currency figures unchanged', () => {
    // The budget, valuations and cash impact are ringgit by definition, and this is the
    // formatter that says so.
    expect(fmtMoney(1980)).toBe('RM 1,980');
  });

  it('shows an em dash rather than a fabricated zero', () => {
    expect(fmtMoney(null)).toBe(EM_DASH);
  });
});

describe('fmtMoneyIn', () => {
  it('names the currency a rounded figure is actually in', () => {
    // The PO worklist committed cash against a mostly-USD book; `RM 1,980` there was a
    // wrong number printed as a fact.
    expect(fmtMoneyIn(1980, 'USD')).toBe('USD 1,980');
  });

  it('writes the base currency with the same glyph as everything else', () => {
    expect(fmtMoneyIn(1980, BASE_CURRENCY)).toBe('RM 1,980');
    expect(fmtMoneyIn(1980, null)).toBe('RM 1,980');
  });

  it('drops the cents, because a committed-cash total is read at a glance', () => {
    expect(fmtMoneyIn(1980.49, 'USD')).toBe('USD 1,980');
  });

  it('shows an em dash rather than a fabricated zero', () => {
    expect(fmtMoneyIn(null, 'USD')).toBe(EM_DASH);
    expect(fmtMoneyIn(Number.NaN, 'USD')).toBe(EM_DASH);
  });
});

describe('fmtTrimmedDecimal', () => {
  it('writes a whole number whole, so the arithmetic lines read as arithmetic', () => {
    expect(fmtTrimmedDecimal(11)).toBe('11');
    expect(fmtTrimmedDecimal(11.0)).toBe('11');
  });

  it('keeps the decimals that carry meaning, up to the asked-for width', () => {
    expect(fmtTrimmedDecimal(11.25)).toBe('11.25');
    expect(fmtTrimmedDecimal(11.25, 1)).toBe('11.3');
  });

  it('separates thousands', () => {
    expect(fmtTrimmedDecimal(12345.5, 1)).toBe('12,345.5');
  });

  it('shows an em dash for a figure the engine never had', () => {
    expect(fmtTrimmedDecimal(null)).toBe(EM_DASH);
    expect(fmtTrimmedDecimal(undefined)).toBe(EM_DASH);
    expect(fmtTrimmedDecimal(Number.NaN)).toBe(EM_DASH);
  });
});

describe('fmtDateTime', () => {
  it('carries the time, because two runs on one day are otherwise the same stamp', () => {
    const shown = fmtDateTime('2026-08-15T09:28:00');
    expect(shown).toContain('2026');
    expect(shown).toMatch(/\d{1,2}:\d{2}/);
  });

  it('shows an em dash for an absent or unreadable stamp', () => {
    expect(fmtDateTime(null)).toBe(EM_DASH);
    expect(fmtDateTime('not a date')).toBe(EM_DASH);
  });
});
