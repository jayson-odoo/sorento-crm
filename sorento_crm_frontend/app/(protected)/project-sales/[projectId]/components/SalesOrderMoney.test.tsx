/**
 * Money arrives as decimal strings and must stay exact.
 *
 * These cases are the ones a float loses: a hundred cents summed one at a time, a
 * five-decimal unit price off a real sales order, and a 1.6 million ringgit total.
 */
import { describe, expect, it } from 'vitest';
import {
  compareMoney,
  formatMoney,
  formatQty,
  formatUnitPrice,
  isZeroMoney,
  sumMoney,
} from './SalesOrderMoney';

describe('sumMoney', () => {
  it('adds cents without drift', () => {
    // 0.07 + 0.01 is 0.07999999999999999 as doubles.
    expect(sumMoney(['0.07', '0.01'])).toBe('0.08');
    expect(sumMoney(Array.from({ length: 100 }, () => '0.01'))).toBe('1.00');
  });

  it('adds a real sales order to the cent', () => {
    expect(sumMoney(['1611107.81', '74677.32'])).toBe('1685785.13');
  });

  it('lines up operands of different precision', () => {
    expect(sumMoney(['392.85000', '0.15'])).toBe('393.00000');
  });

  it('skips values that are not numbers rather than treating them as zero', () => {
    expect(sumMoney(['12.50', null, undefined, '', 'n/a'])).toBe('12.50');
    expect(sumMoney([])).toBe('0');
  });
});

describe('compareMoney', () => {
  it('compares on the digits, not on a parsed float', () => {
    expect(compareMoney('13.77', '13.770')).toBe(0);
    expect(compareMoney('13.77', '13.78')).toBe(-1);
    expect(compareMoney('1611107.81', '1611107.80')).toBe(1);
  });
});

describe('isZeroMoney', () => {
  it('recognises the zero-priced companion of a set', () => {
    expect(isZeroMoney('0.00000')).toBe(true);
    expect(isZeroMoney('0')).toBe(true);
    expect(isZeroMoney('0.01')).toBe(false);
    expect(isZeroMoney(null)).toBe(false);
  });
});

describe('formatting', () => {
  it('groups and keeps two decimals on money', () => {
    expect(formatMoney('1611107.81')).toBe('RM 1,611,107.81');
    expect(formatMoney('6696')).toBe('RM 6,696.00');
    expect(formatMoney('0.005')).toBe('RM 0.01');
    expect(formatMoney(null)).toBe('');
  });

  it('trims a unit price to what the document actually carries', () => {
    expect(formatUnitPrice('392.85000')).toBe('392.85');
    expect(formatUnitPrice('11.16000')).toBe('11.16');
    expect(formatUnitPrice('0.00000')).toBe('0.00');
    expect(formatUnitPrice('1950.00000')).toBe('1,950.00');
  });

  it('keeps only meaningful decimals on a quantity', () => {
    expect(formatQty('1800')).toBe('1,800');
    expect(formatQty('135.500')).toBe('135.5');
    expect(formatQty('135')).toBe('135');
  });
});
