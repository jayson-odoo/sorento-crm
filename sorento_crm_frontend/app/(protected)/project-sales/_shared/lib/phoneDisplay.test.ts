/** Owner hand test 10 Nov: phones stored as E.164 read in one local format everywhere. */
import { describe, expect, it } from 'vitest';
import { formatPhone } from './phoneDisplay';

describe('formatPhone', () => {
  it.each([
    ['+60129876543', '012-987 6543'],
    ['012-987 6543', '012-987 6543'],
    ['60320000002', '03-2000 0002'],
    ['+601112345678', '011-1234 5678'],
  ])('%s reads %s', (raw, shown) => {
    expect(formatPhone(raw)).toBe(shown);
  });

  it('a number it cannot read is shown as typed, and blank stays blank', () => {
    expect(formatPhone('03-1111')).toBe('03-1111');
    expect(formatPhone(null)).toBe('');
    expect(formatPhone('')).toBe('');
  });

  it('a foreign number keeps its country code', () => {
    expect(formatPhone('+6591234567')).toBe('+65 9123 4567');
  });
});
