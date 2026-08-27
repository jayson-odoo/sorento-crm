import { describe, expect, it } from 'vitest';
import {
  describeLevelSuggestion,
  levelActionLabel,
  levelKey,
  levelRowsForExport,
  levelTerms,
  type LevelSuggestion,
} from './levelSuggestion';

/**
 * The wording over the level suggestion.
 *
 * Rules under test: the row states the ACTION ("Set AutoCount level to N"), the current
 * level always travels beside it, and the popup names the THREE TERMS the level is made
 * of (AC-R11: ADU a day, the lead time, the safety stock) - never a bare verdict.
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
  amended_level: null,
  amended_at: null,
  suggested_quantity: null,
  master_reorder_quantity: null,
  basis: {
    // 900 over 90 days = 10 a day; a 30 day lead needs 300, 14 days of safety adds 140.
    adu: 10,
    lead_time_days: 30,
    lead_time_source: 'supplier',
    safety_days: 14,
    safety_stock: 140,
    window_days: 90,
    window_qty: 900,
    raw_level: 440,
    months: [],
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
    expect(describeLevelSuggestion(entry({ suggested_level: 440 }))).toBe(
      '900 left the warehouses over the last 90 days, so 10 a day. ' +
        'A 30 day lead needs 300, and 14 days of safety adds 140: 440, rounded up to 440.',
    );
  });

  it('says so when the 30 day lead time is only a stand-in', () => {
    const text = describeLevelSuggestion(
      entry({ basis: { ...entry().basis, lead_time_source: 'default' } }),
    );
    expect(text).toMatch(/No lead time is on file/i);
  });

  it('a no-movement zero says nothing moved, never a bare 0', () => {
    const text = describeLevelSuggestion(
      entry({
        suggested_level: 0,
        basis: { ...entry().basis, adu: 0, window_qty: 0, safety_stock: 0, raw_level: 0, no_movement: true },
      }),
    );
    expect(text).toMatch(/nothing left the warehouses/i);
  });
});

describe('levelTerms', () => {
  it('names the three terms the level is made of, each with its figure', () => {
    expect(levelTerms(entry())).toEqual([
      { label: 'ADU', value: '10 / day' },
      { label: 'Lead time', value: '30 d' },
      { label: 'Safety', value: '140 (14 d)' },
    ]);
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
      engine_level: null,
      adu: 10,
      lead_time_days: 30,
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
    amended_level: null, amended_at: null, suggested_quantity: null,
    master_reorder_quantity: null,
    basis: { adu: 0, lead_time_days: 30, lead_time_source: 'default', safety_days: 14,
             safety_stock: 0, window_days: 90, window_qty: 0, raw_level: 0, months: [],
             no_movement: true },
    ...over,
  };
}

describe('the amendment (S14)', () => {
  it('the buyer’s figure leads, with the engine’s number still in sight', () => {
    const got = levelActionLabel(entry({ amended_level: 30 }));
    expect(got).toEqual({
      label: 'Set AutoCount level to 30',
      detail: 'you set this; engine said 24, now 20',
      changed: true,
    });
  });

  it('an amendment back to the current level means no trip to AutoCount', () => {
    const got = levelActionLabel(entry({ amended_level: 20 }));
    expect(got.changed).toBe(false);
    expect(got.label).toBe('Level 20 still fits');
  });

  it('the export carries the amended figure and names the engine’s beside it', () => {
    const rows = levelRowsForExport({ a: entry({ amended_level: 30 }) });
    expect(rows[0].suggested_level).toBe(30);
    expect(rows[0].engine_level).toBe(24);
  });

  it('an unamended row exports the engine figure with no separate engine column value', () => {
    const rows = levelRowsForExport({ a: entry() });
    expect(rows[0].suggested_level).toBe(24);
    expect(rows[0].engine_level).toBeNull();
  });
});
