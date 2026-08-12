/**
 * P4 - the decimal-safe arithmetic the confirm screen's headline number depends on.
 *
 * These are the tests that would fail if anyone reintroduced `Number(value)`: the 52 line
 * sum, the qty times price check, and the cent-exact difference between our total and the
 * one printed on the paper.
 */
import { describe, expect, it } from 'vitest';
import {
  compareMoney,
  formatMyrExact,
  formatQty,
  isDecimalString,
  isMoneyZero,
  multiplyMoney,
  subtractMoney,
  sumMoney,
} from '../../_shared/lib/money';

describe('money', () => {
  it('sums two-decimal strings without float drift', () => {
    // 0.1 + 0.2 as floats is 0.30000000000000004; as cents it is 30.
    expect(sumMoney(['0.10', '0.20'])).toBe('0.30');
    expect(sumMoney(['364171.95', '1446468.67'])).toBe('1810640.62');
  });

  it('sums a long list of lines exactly', () => {
    const values = Array.from({ length: 52 }, () => '392.85');
    expect(sumMoney(values)).toBe('20428.20');
  });

  it('refuses to guess at a value that is not a decimal', () => {
    expect(sumMoney(['1.00', 'about ten'])).toBeNull();
    expect(subtractMoney('1.00', null)).toBeNull();
    expect(multiplyMoney('two', '10.00')).toBeNull();
    expect(isDecimalString('1,000.00')).toBe(false);
    expect(isDecimalString('1000.00')).toBe(true);
  });

  it('subtracts signed, to the cent', () => {
    expect(subtractMoney('1800000.00', '1810640.62')).toBe('-10640.62');
    expect(subtractMoney('1810640.62', '1810640.62')).toBe('0.00');
    expect(isMoneyZero('0.00')).toBe(true);
    expect(isMoneyZero('-0.01')).toBe(false);
  });

  it('multiplies a quantity by a unit price the way an amount column does', () => {
    expect(multiplyMoney('927', '392.85')).toBe('364171.95');
    expect(multiplyMoney('16', '37.50')).toBe('600.00');
    // A fractional quantity still lands on the cent.
    expect(multiplyMoney('1.5', '10.01')).toBe('15.02');
  });

  it('compares without parsing floats', () => {
    expect(compareMoney('10.00', '10.00')).toBe(0);
    expect(compareMoney('9.99', '10.00')).toBe(-1);
    expect(compareMoney('10.01', '10.00')).toBe(1);
    expect(compareMoney('10.01', 'x')).toBeNull();
  });

  it('groups ringgit from the string, keeping both cents', () => {
    expect(formatMyrExact('1810640.62')).toBe('RM 1,810,640.62');
    expect(formatMyrExact('392.85')).toBe('RM 392.85');
    expect(formatMyrExact('0.05')).toBe('RM 0.05');
    expect(formatMyrExact('-10640.62')).toBe('-RM 10,640.62');
    expect(formatMyrExact(null)).toBe('-');
  });

  it('shows a quantity as written rather than padded', () => {
    expect(formatQty('927')).toBe('927');
    expect(formatQty('927.0000')).toBe('927');
    expect(formatQty('1.50')).toBe('1.5');
  });
});
