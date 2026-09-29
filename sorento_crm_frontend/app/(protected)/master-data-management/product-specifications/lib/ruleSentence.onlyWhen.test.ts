/**
 * N-9 (review round 2) - "Only when" names the other specification by its label,
 * and when the registry no longer carries it, by a humanised key: never the raw
 * snake_case key.
 */
import { describe, it, expect } from 'vitest';
import { onlyWhenCell } from './ruleSentence';
import type { SpecRuleBuilder } from '../types/productSpec.types';

const rule: SpecRuleBuilder = {
  kind: 'words',
  words: ['ROSE GOLD'],
  value: 'rose_gold',
  only_when: { spec: 'from_category', is: false, values: ['rose_gold'] },
};

describe('onlyWhenCell - never the raw key (N-9)', () => {
  it('falls back to a humanised key when the spec is not in the registry', () => {
    expect(onlyWhenCell(rule, () => undefined)).toBe('From category is not: Rose gold');
  });

  it('still prefers the registry label when there is one', () => {
    expect(
      onlyWhenCell(rule, () => ({ label: 'Product class', value_labels: {} }) as never),
    ).toBe('Product class is not: Rose gold');
  });
});
