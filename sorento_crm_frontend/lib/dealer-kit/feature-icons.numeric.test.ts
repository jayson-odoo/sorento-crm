import { describe, expect, it } from 'vitest';

import { numericText } from './feature-icons';

describe('numericText mirrors the backend numeric_value_text', () => {
  it('normalises numbers and leaves non-numbers alone', () => {
    expect(numericText('150.0')).toBe('150');
    expect(numericText(150)).toBe('150');
    expect(numericText('150.50')).toBe('150.5');
    expect(numericText(' 12 ')).toBe('12');
    expect(numericText('long')).toBeNull();
    expect(numericText('')).toBeNull();
    expect(numericText('0x10')).toBeNull();
  });
});
