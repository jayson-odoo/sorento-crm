/**
 * PLAN-plan-list-tile-sheet-one-scope.md, AC-5b (7e3960e38) - `filterGroupAsksForRecType`
 * walks an applied `ListQueryFilterGroup` (the dynamic filter builder's own wire shape,
 * `lib/list-query/listQueryService.ts`) looking for a `rec_type` condition (the builder's
 * field, `planLineFilterFields.ts:39-43`) asking for a given value via `eq` or `in`, at any
 * nesting depth - AND/OR both, since a buyer can wrap a condition inside either. This is
 * the same predicate `PlanLinesSection.visibleLines` is expected to call to decide whether
 * to reveal the hidden-by-default rows (see the AC-5b describe block in
 * `PlanLinesSection.visibleLines.test.tsx`, which drives it end to end through the mocked
 * grid rather than importing this helper directly).
 *
 * Red today: `lib/planLineFilters.ts` does not exist.
 */
import { describe, it, expect } from 'vitest';
import type { ListQueryFilterGroup } from '@/lib/list-query/listQueryService';
import { filterGroupAsksForRecType } from './planLineFilters';

const eq = (value: unknown): ListQueryFilterGroup => ({
  op: 'and',
  children: [{ field_key: 'rec_type', op: 'eq', value }],
});

const inList = (value: unknown): ListQueryFilterGroup => ({
  op: 'and',
  children: [{ field_key: 'rec_type', op: 'in', value }],
});

describe('filterGroupAsksForRecType', () => {
  it('is false for null / an empty group', () => {
    expect(filterGroupAsksForRecType(null, 'covered_by_stock')).toBe(false);
    expect(filterGroupAsksForRecType({ op: 'and', children: [] }, 'covered_by_stock')).toBe(false);
  });

  it('is true for a top-level "rec_type eq covered_by_stock" condition', () => {
    expect(filterGroupAsksForRecType(eq('covered_by_stock'), 'covered_by_stock')).toBe(true);
  });

  it('is true for "rec_type in [covered_by_stock]" (single-value list)', () => {
    expect(filterGroupAsksForRecType(inList(['covered_by_stock']), 'covered_by_stock')).toBe(true);
  });

  it('is true for "rec_type in [...]" when covered_by_stock is one of SEVERAL values', () => {
    expect(
      filterGroupAsksForRecType(inList(['buy', 'covered_by_stock', 'needs_level']), 'covered_by_stock'),
    ).toBe(true);
  });

  it('is true nested one group deep under AND', () => {
    const group: ListQueryFilterGroup = { op: 'and', children: [eq('covered_by_stock')] };
    expect(filterGroupAsksForRecType(group, 'covered_by_stock')).toBe(true);
  });

  it('is true nested one group deep under OR', () => {
    const group: ListQueryFilterGroup = { op: 'or', children: [inList(['covered_by_stock'])] };
    expect(filterGroupAsksForRecType(group, 'covered_by_stock')).toBe(true);
  });

  it('is false when the condition targets a DIFFERENT field', () => {
    const group: ListQueryFilterGroup = {
      op: 'and',
      children: [{ field_key: 'decision_state', op: 'eq', value: 'covered_by_stock' }],
    };
    expect(filterGroupAsksForRecType(group, 'covered_by_stock')).toBe(false);
  });

  it('is false when rec_type is compared to a DIFFERENT value', () => {
    expect(filterGroupAsksForRecType(eq('buy'), 'covered_by_stock')).toBe(false);
    expect(filterGroupAsksForRecType(inList(['buy', 'needs_level']), 'covered_by_stock')).toBe(false);
  });

  it('is false for an operator that is not eq/in (e.g. contains)', () => {
    const group: ListQueryFilterGroup = {
      op: 'and',
      children: [{ field_key: 'rec_type', op: 'contains', value: 'covered_by_stock' }],
    };
    expect(filterGroupAsksForRecType(group, 'covered_by_stock')).toBe(false);
  });

  it('is true when buried alongside an unrelated sibling condition', () => {
    const group: ListQueryFilterGroup = {
      op: 'and',
      children: [
        { field_key: 'sku', op: 'contains', value: 'B2154' },
        eq('covered_by_stock'),
      ],
    };
    expect(filterGroupAsksForRecType(group, 'covered_by_stock')).toBe(true);
  });
});
