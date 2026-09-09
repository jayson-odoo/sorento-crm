import { describe, expect, it } from 'vitest';
import { formatRatio } from './productCompanion';

describe('formatRatio', () => {
  it('trims trailing zeros off a NUMERIC(15,4) string', () => {
    expect(formatRatio('1.0000')).toBe('1');
    expect(formatRatio('0.5000')).toBe('0.5');
    expect(formatRatio('1.2500')).toBe('1.25');
  });

  it('leaves an already-trimmed value alone', () => {
    expect(formatRatio('1')).toBe('1');
    expect(formatRatio('0.5')).toBe('0.5');
  });

  it('handles a plain number too', () => {
    expect(formatRatio(1)).toBe('1');
  });

  it('is blank for null/undefined and passes through anything not numeric', () => {
    expect(formatRatio(null)).toBe('');
    expect(formatRatio(undefined)).toBe('');
    expect(formatRatio('n/a')).toBe('n/a');
  });
});
