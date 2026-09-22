/**
 * compareRows - pure helpers behind the Compare tab's grid + download (small-fix track,
 * PLAN-autocount-compare-tab-detail.md). No React, no DataGrid - see
 * `PullCompareTab.test.tsx` for the rendered assertions these back.
 */
import { describe, it, expect } from 'vitest';
import { formatCompareValue, fieldLabel, buildCompareRows } from './compareRows';
import type { AutocountComparePullResult } from '../types/autocountPull.types';

describe('formatCompareValue', () => {
  it('formats booleans as Active / Inactive, never true/false', () => {
    expect(formatCompareValue(true)).toBe('Active');
    expect(formatCompareValue(false)).toBe('Inactive');
  });

  it('formats null/undefined as a dash', () => {
    expect(formatCompareValue(null)).toBe('-');
    expect(formatCompareValue(undefined as unknown as null)).toBe('-');
  });

  it('formats an empty string as a dash too (review S1: backend sends "" for blank description/item_group/item_brand)', () => {
    expect(formatCompareValue('')).toBe('-');
  });

  it('formats 0 as "0", not a dash', () => {
    expect(formatCompareValue(0)).toBe('0');
  });

  it('formats numbers and non-blank strings as themselves', () => {
    expect(formatCompareValue(12)).toBe('12');
    expect(formatCompareValue('10.00')).toBe('10.00');
  });
});

describe('fieldLabel', () => {
  it('maps known backend field keys to human labels', () => {
    expect(fieldLabel('description')).toBe('Description');
    expect(fieldLabel('item_group')).toBe('Item Group');
    expect(fieldLabel('item_brand')).toBe('Item Brand');
    expect(fieldLabel('price')).toBe('Price');
    expect(fieldLabel('on_hand_qty')).toBe('On Hand Qty');
  });

  it('labels is_active "Is Active" - matches the manual template header, and never collides with the Active/Inactive VALUE cells (captain ruling N7)', () => {
    expect(fieldLabel('is_active')).toBe('Is Active');
  });

  it('falls back to the raw key for anything unknown - never renders it, but never crashes either', () => {
    expect(fieldLabel('some_new_field')).toBe('some_new_field');
  });
});

describe('buildCompareRows', () => {
  function result(overrides: Partial<AutocountComparePullResult> = {}): AutocountComparePullResult {
    return {
      summary: {
        filename: 'check.xlsx', compared_at: '2026-09-22T00:00:00Z',
        total: 1, matched: 0, different: 1, only_in_excel: 0, only_in_pull: 0,
      },
      differences: [],
      only_in_excel: [],
      only_in_pull: [],
      ...overrides,
    };
  }

  it('formats a boolean difference and gives the field a human label', () => {
    const rows = buildCompareRows(
      result({ differences: [{ item_code: 'SRT-1', field: 'is_active', excel: true, pull: false }] }),
      'products',
    );
    expect(rows).toEqual([
      { item_code: 'SRT-1', location: undefined, field: 'Is Active', excel: 'Active', pull: 'Inactive' },
    ]);
  });

  it('adds one row per only_in_excel code, labelled "Only in your Excel"', () => {
    const rows = buildCompareRows(result({ only_in_excel: ['SRT-2'] }), 'products');
    expect(rows).toEqual([
      { item_code: 'SRT-2', location: undefined, field: 'Only in your Excel', excel: 'Present', pull: 'Missing' },
    ]);
  });

  it('adds one row per only_in_pull code, labelled "Only in AutoCount"', () => {
    const rows = buildCompareRows(result({ only_in_pull: ['SRT-3'] }), 'products');
    expect(rows).toEqual([
      { item_code: 'SRT-3', location: undefined, field: 'Only in AutoCount', excel: 'Missing', pull: 'Present' },
    ]);
  });

  it('splits a stock "code|location" only-in label into item_code and location for stock_balances', () => {
    const rows = buildCompareRows(result({ only_in_excel: ['SRT-4|MAIN'] }), 'stock_balances');
    expect(rows).toEqual([
      { item_code: 'SRT-4', location: 'MAIN', field: 'Only in your Excel', excel: 'Present', pull: 'Missing' },
    ]);
  });

  it('never splits a products only-in code, even one that happens to contain "|" (review S2: a product item code is raw, not a code|location pair)', () => {
    const rows = buildCompareRows(result({ only_in_excel: ['A|B'] }), 'products');
    expect(rows).toEqual([
      { item_code: 'A|B', location: undefined, field: 'Only in your Excel', excel: 'Present', pull: 'Missing' },
    ]);
  });

  it('combines differences + both only-in lists into one array, in that order', () => {
    const rows = buildCompareRows(
      result({
        differences: [{ item_code: 'A', field: 'price', excel: '10.00', pull: '12.00' }],
        only_in_excel: ['B'],
        only_in_pull: ['C'],
      }),
      'products',
    );
    expect(rows.map((r) => r.item_code)).toEqual(['A', 'B', 'C']);
    expect(rows).toHaveLength(3);
  });
});
