import { describe, expect, it } from 'vitest';
import {
  describeLevelSuggestion,
  levelActionLabel,
  levelKey,
  levelRowsForExport,
  type LevelSuggestion,
} from './levelSuggestion';

/**
 * The wording over the S13f level suggestion.
 *
 * Rules under test: the row states the ACTION ("Set AutoCount level to N"), the current
 * level always travels beside it, and the popup shows the sums - never a bare verdict.
 */

const entry = (over: Partial<LevelSuggestion> = {}): LevelSuggestion => ({
  product_id: 'p1',
  warehouse_id: 'w1',
  product_code: 'SRT-100',
  product_name: 'Basin',
  warehouse_code: 'BRW',
  warehouse_name: 'Branch West',
  current_level: 20,
  current_source: 'autocount',
  suggested_level: 24,
  suggested_at: '2026-08-10T00:00:00',
  basis: {
    months: [],
    months_studied: 3,
    total_qty: 36,
    avg_monthly: 12,
    cover_months: 2,
    raw_level: 24,
    moq: null,
    order_multiple: null,
    trend: 'rising',
    no_movement: false,
  },
  ...over,
});

describe('levelActionLabel', () => {
  it('states the action with both numbers, because "set to 24" means nothing without "now 20"', () => {
    expect(levelActionLabel(entry())).toEqual({
      label: 'Set AutoCount level to 24',
      detail: 'now 20',
      changed: true,
    });
  });

  it('says none set rather than implying the current level is zero', () => {
    const got = levelActionLabel(entry({ current_level: null, current_source: null }));
    expect(got.detail).toBe('none set today');
    expect(got.changed).toBe(true);
  });

  it('a suggestion equal to the level is confirmation, not a change', () => {
    const got = levelActionLabel(entry({ suggested_level: 20 }));
    expect(got.label).toBe('Level 20 still fits');
    expect(got.changed).toBe(false);
  });
});

describe('describeLevelSuggestion', () => {
  it('walks the arithmetic in words a person says', () => {
    expect(describeLevelSuggestion(entry())).toBe(
      'Averaged 12 a month over the last 3 months; 2 months of cover makes 24. Orders are rising, so it rounds up.',
    );
  });

  it('says the rounding leaned down when the book is dying', () => {
    const text = describeLevelSuggestion(
      entry({
        suggested_level: 28,
        basis: { ...entry().basis, avg_monthly: 11.33, cover_months: 2.5, raw_level: 28.33, trend: 'falling' },
      }),
    );
    expect(text).toMatch(/rounds down/);
  });

  it('names the supplier constraint when one lifted the number', () => {
    const text = describeLevelSuggestion(
      entry({
        suggested_level: 30,
        basis: { ...entry().basis, moq: 30, raw_level: 24 },
      }),
    );
    expect(text).toMatch(/minimum order of 30/i);
  });

  it('a no-movement zero says nothing moved, never a bare 0', () => {
    const text = describeLevelSuggestion(
      entry({
        suggested_level: 0,
        basis: { ...entry().basis, avg_monthly: 0, total_qty: 0, raw_level: 0, no_movement: true, trend: null },
      }),
    );
    expect(text).toMatch(/nothing left this location/i);
  });
});

describe('levelKey', () => {
  it('matches the backend key, warehouse optional', () => {
    expect(levelKey('p1', 'w1')).toBe('p1:w1');
    expect(levelKey('p1', null)).toBe('p1:');
    expect(levelKey(null, 'w1')).toBeNull();
  });
});

describe('levelRowsForExport', () => {
  it('lists only the CHANGES, named by code, ready for the AutoCount edit', () => {
    const rows = levelRowsForExport({
      a: entry(),
      b: entry({ product_code: 'SRT-200', suggested_level: 20 }), // unchanged
    });
    expect(rows).toHaveLength(1);
    expect(rows[0]).toEqual({
      product_code: 'SRT-100',
      product_name: 'Basin',
      warehouse: 'BRW',
      current_level: 20,
      suggested_level: 24,
      trend: 'rising',
    });
  });
});

describe('the zero-on-nothing rule', () => {
  it('a suggested 0 where none is set asks for nothing, and says why', () => {
    const got = levelActionLabel(
      entryForZero(),
    );
    expect(got).toEqual({ label: 'No level needed', detail: 'nothing moved', changed: false });
  });

  it('but a stored level a dead product should drop to 0 IS a change', () => {
    const got = levelActionLabel(entryForZero({ current_level: 15 }));
    expect(got.label).toBe('Set AutoCount level to 0');
    expect(got.changed).toBe(true);
  });
});

function entryForZero(over: Partial<LevelSuggestion> = {}): LevelSuggestion {
  return {
    product_id: 'p9', warehouse_id: 'w1', product_code: 'SRT-900', product_name: 'Dust',
    warehouse_code: 'BRW', warehouse_name: 'Branch West',
    current_level: null, current_source: null, suggested_level: 0, suggested_at: null,
    basis: { months: [], months_studied: 3, total_qty: 0, avg_monthly: 0, cover_months: 2,
             raw_level: 0, moq: null, order_multiple: null, trend: null, no_movement: true },
    ...over,
  };
}
