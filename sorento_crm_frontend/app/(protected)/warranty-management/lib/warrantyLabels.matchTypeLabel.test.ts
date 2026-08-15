/**
 * `formatMatchTypeLabel` - S7b Phase 2c follow-up gate, item 2.
 *
 * AC-P24 "strict at write, tolerant at read": a `match_type` the frontend has
 * no label for must still render SOMETHING readable: the RAW stored value,
 * not an invented placeholder word like "Unknown". An admin looking at a
 * legacy row (written before the frontend knew this match_type, or by a
 * migration) needs to see what is actually in the database column, not a
 * label that hides it. Pinning all four known values directly (not only
 * through the `RulesTab` grid) so a future "tidy this up" refactor of the
 * label map cannot quietly swap the fallback for a placeholder without a
 * failing test at the source of the behaviour.
 */
import { describe, it, expect } from 'vitest';
import { formatMatchTypeLabel } from './warrantyLabels';

describe('formatMatchTypeLabel', () => {
  it('labels the four known match types', () => {
    expect(formatMatchTypeLabel('model_list')).toBe('Model list');
    expect(formatMatchTypeLabel('model_prefix')).toBe('Model prefix');
    expect(formatMatchTypeLabel('series')).toBe('Series');
    expect(formatMatchTypeLabel('category')).toBe('Category');
  });

  it('falls back to the RAW stored value for an unknown match_type, not a placeholder', () => {
    expect(formatMatchTypeLabel('something_new')).toBe('something_new');
    // Not "Unknown", not "-", not empty: the exact column value survives.
    expect(formatMatchTypeLabel('legacy_sku_regex')).toBe('legacy_sku_regex');
  });

  it('the fallback is case-preserving and does not normalize the raw value', () => {
    expect(formatMatchTypeLabel('Legacy_Value')).toBe('Legacy_Value');
  });
});
