/** Owner hand test 10 Nov: phones stored as E.164 read in one local format everywhere. */
import { describe, expect, it } from 'vitest';
import { formatPhone } from './phoneDisplay';

describe('formatPhone', () => {
  it.each([
    ['+60120000501', '012-000 0501'],
    ['012-000 0501', '012-000 0501'],
    ['60320000002', '03-2000 0002'],
    ['+601111111111', '011-1111 1111'],
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
