/**
 * Quantity precision, owned by the UOM (plan section 6.4, AC-F12).
 *
 * The pair the AC is written against: a count unit (`EA`, dp 0) refuses `2.5`;
 * a measure unit (`kg`, dp 3) accepts `2.75`. Every boundary from dp 0 through
 * dp 4 is pinned here, plus the invalid-input fallbacks the frozen snapshot can
 * arrive in (null, undefined, out of range, non-finite).
 */
import { describe, it, expect } from 'vitest';
import {
  DEFAULT_DECIMAL_PLACES,
  decimalPlacesOf,
  decimalsIn,
  exceedsPrecision,
  fmtQty,
  precisionError,
  precisionHint,
  sanitizeQtyInput,
} from './qtyPrecision';

describe('decimalPlacesOf - resolving the frozen snapshot', () => {
  it('resolves null and undefined to the rollout fallback of 0', () => {
    expect(decimalPlacesOf(null)).toBe(DEFAULT_DECIMAL_PLACES);
    expect(decimalPlacesOf(undefined)).toBe(0);
  });

  it('passes through every in-range value 0..4', () => {
    expect(decimalPlacesOf(0)).toBe(0);
    expect(decimalPlacesOf(1)).toBe(1);
    expect(decimalPlacesOf(2)).toBe(2);
    expect(decimalPlacesOf(3)).toBe(3);
    expect(decimalPlacesOf(4)).toBe(4);
  });

  it('clamps a value above 4 down to 4', () => {
    expect(decimalPlacesOf(5)).toBe(4);
    expect(decimalPlacesOf(9)).toBe(4);
  });

  it('clamps a negative value up to 0', () => {
    expect(decimalPlacesOf(-1)).toBe(0);
  });

  it('truncates a fractional dp itself rather than rounding it', () => {
    expect(decimalPlacesOf(2.9)).toBe(2);
  });

  it('resolves a non-finite value (NaN, Infinity) to the fallback', () => {
    expect(decimalPlacesOf(Number.NaN)).toBe(0);
    expect(decimalPlacesOf(Number.POSITIVE_INFINITY)).toBe(0);
  });
});

describe('decimalsIn - how many fractional digits are actually typed', () => {
  it('reads 0 for a whole number with no separator', () => {
    expect(decimalsIn('25')).toBe(0);
  });

  it('reads the exact count of typed fractional digits', () => {
    expect(decimalsIn('2.5')).toBe(1);
    expect(decimalsIn('2.75')).toBe(2);
    expect(decimalsIn('2.755')).toBe(3);
  });

  it('ignores trailing zeros - a typed 2.50 carries one meaningful digit', () => {
    expect(decimalsIn('2.50')).toBe(1);
    expect(decimalsIn('2.500')).toBe(1);
  });

  it('reads 0 for a bare trailing dot', () => {
    expect(decimalsIn('2.')).toBe(0);
  });

  it('reads 0 for an empty string', () => {
    expect(decimalsIn('')).toBe(0);
  });
});

describe('sanitizeQtyInput - keeps a quantity typeable at its own precision', () => {
  it('strips the decimal point entirely at dp 0, so a fraction can never be typed', () => {
    expect(sanitizeQtyInput('2.5', 0)).toBe('25');
    expect(sanitizeQtyInput('12.99', 0)).toBe('1299');
  });

  it('strips non-digit, non-dot characters at any precision', () => {
    expect(sanitizeQtyInput('2a.5b', 0)).toBe('25');
    expect(sanitizeQtyInput('kg2.5', 3)).toBe('2.5');
  });

  it('caps the fractional tail to the allowed dp, digit by digit', () => {
    expect(sanitizeQtyInput('2.7555', 3)).toBe('2.755');
    expect(sanitizeQtyInput('2.7', 3)).toBe('2.7');
    expect(sanitizeQtyInput('2.75', 1)).toBe('2.7');
  });

  it('keeps exactly one separator when more than one is typed', () => {
    expect(sanitizeQtyInput('2..5.5', 3)).toBe('2.55');
  });

  it('passes a bare integer through untouched at any dp above 0', () => {
    expect(sanitizeQtyInput('25', 4)).toBe('25');
  });

  it('keeps a trailing dot with an empty fraction, so typing a dot is not silently reverted', () => {
    expect(sanitizeQtyInput('2.', 2)).toBe('2.');
  });
});

describe('precisionHint / precisionError - the words at each boundary', () => {
  it('reads "Whole units only" at dp 0, with the unit named', () => {
    expect(precisionHint(0, 'EA')).toBe('Whole units only (EA)');
    expect(precisionError(0, 'EA')).toBe('Whole units only for EA. Remove the decimals.');
  });

  it('omits the unit parenthetical when none is given', () => {
    expect(precisionHint(0, null)).toBe('Whole units only');
    expect(precisionHint(0, undefined)).toBe('Whole units only');
  });

  it('singularises "decimal place" at dp 1', () => {
    expect(precisionHint(1, 'L')).toBe('Up to 1 decimal place (L)');
  });

  it('pluralises "decimal places" above dp 1', () => {
    expect(precisionHint(2, 'L')).toBe('Up to 2 decimal places (L)');
    expect(precisionHint(3, 'kg')).toBe('Up to 3 decimal places (kg)');
    expect(precisionHint(4, 'kg')).toBe('Up to 4 decimal places (kg)');
  });

  it('words the refusal the same way for every dp above 0', () => {
    expect(precisionError(3, 'kg')).toBe('Up to 3 decimal places for kg.');
  });
});

describe('exceedsPrecision - AC-F12, the exact pair', () => {
  it('dp 0 (EA) rejects a typed 2.5', () => {
    expect(exceedsPrecision('2.5', 0)).toBe(true);
  });

  it('dp 3 (kg) accepts a typed 2.75', () => {
    expect(exceedsPrecision('2.75', 3)).toBe(false);
  });

  it('accepts a whole number at dp 0', () => {
    expect(exceedsPrecision('10', 0)).toBe(false);
  });

  it('rejects a 4th fractional digit at dp 3', () => {
    expect(exceedsPrecision('2.7555', 3)).toBe(true);
  });

  it('accepts exactly dp fractional digits at dp 3', () => {
    expect(exceedsPrecision('2.755', 3)).toBe(false);
  });

  it('accepts up to dp 4 fractional digits', () => {
    expect(exceedsPrecision('1.2345', 4)).toBe(false);
    expect(exceedsPrecision('1.23456', 4)).toBe(true);
  });

  it('accepts fewer fractional digits than the dp allows', () => {
    expect(exceedsPrecision('2.5', 3)).toBe(false);
  });

  it('ignores trailing zeros when counting fractional digits', () => {
    expect(exceedsPrecision('2.500', 1)).toBe(false);
  });
});

describe('fmtQty - never padded, never truncated', () => {
  it('renders null and undefined as an em dash placeholder', () => {
    expect(fmtQty(null)).toBe('-');
    expect(fmtQty(undefined)).toBe('-');
  });

  it('renders a non-finite value as the placeholder rather than NaN', () => {
    expect(fmtQty(Number.NaN)).toBe('-');
  });

  it('renders a whole number with no fractional digits at dp 0', () => {
    expect(fmtQty(600, 0)).toBe('600');
  });

  it('renders exactly the fractional digits present, at dp 3', () => {
    expect(fmtQty(2.75, 3)).toBe('2.75');
    expect(fmtQty(2.5, 3)).toBe('2.5');
  });

  it('groups thousands with a comma', () => {
    expect(fmtQty(12345, 0)).toBe('12,345');
  });

  it('defaults dp to 0 when omitted', () => {
    expect(fmtQty(600)).toBe('600');
  });

  it('clamps a dp above 4 down to 4 when formatting, rounding the extra digits', () => {
    expect(fmtQty(1.23456, 6)).toBe('1.2346');
  });

  it('clamps a negative dp up to 0 when formatting', () => {
    expect(fmtQty(2.6, -1)).toBe('3');
  });
});
