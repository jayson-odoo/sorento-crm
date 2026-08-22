/**
 * Code review finding S12: `reorder_level` is set by the planning-mode switch
 * (Auto/Manual), never chosen as a create option in the Add modal - it must stay out of
 * `POLICY_TYPE_OPTIONS` while remaining readable via `POLICY_TYPE_LABEL` for a row that
 * already carries it (the grid / preview still need the wording).
 */
import { describe, it, expect } from 'vitest';
import { POLICY_TYPE_LABEL, POLICY_TYPE_OPTIONS } from './labels';

describe('POLICY_TYPE_OPTIONS', () => {
  it('does not offer reorder_level as a create option', () => {
    expect(POLICY_TYPE_OPTIONS.map((o) => o.value)).not.toContain('reorder_level');
  });

  it('offers exactly the three create-able policy types', () => {
    expect(POLICY_TYPE_OPTIONS.map((o) => o.value)).toEqual([
      'reorder_point',
      'periodic_review',
      'min_max',
    ]);
  });
});

describe('POLICY_TYPE_LABEL', () => {
  it('still labels reorder_level for the grid / preview to read', () => {
    expect(POLICY_TYPE_LABEL.reorder_level).toBe('Reorder level');
  });
});
