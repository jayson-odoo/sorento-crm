/**
 * Round-trip tests for buildDetailSearch / parseDetailSearch.
 *
 * UAC-10: returning to the list from detail must preserve the
 * filter/search/sort state carried via the detail URL search params, round-trip
 * through buildDataGridParams.
 */
import { describe, it, expect } from 'vitest';

import { DEFAULT_PAGE_SIZES } from '@/components/ui/data-grid-pagination';

import {
  MAX_LIST_PAGE_SIZE,
  buildDetailSearch,
  parseDetailSearch,
} from './listNavQuery';

describe('listNavQuery round-trip', () => {
  it('preserves query, sort, dir, and extra filters through build -> parse', () => {
    const search = buildDetailSearch(
      {
        pageIndex: 2, // -> page 3
        pageSize: 25,
        sorting: [{ id: 'customer_name', desc: true }],
        searchQuery: '04',
      },
      { assigned_to: 'agent-1', status: 'responded' },
    );

    const parsed = parseDetailSearch(new URLSearchParams(search));

    expect(parsed.pageIndex).toBe(2);
    expect(parsed.pageSize).toBe(25);
    expect(parsed.searchQuery).toBe('04');
    expect(parsed.sorting).toEqual([{ id: 'customer_name', desc: true }]);
    expect(parsed.filters.assigned_to).toBe('agent-1');
    expect(parsed.filters.status).toBe('responded');
  });

  it('round-trips an ascending sort', () => {
    const search = buildDetailSearch({
      pageIndex: 0,
      pageSize: 50,
      sorting: [{ id: 'complaint_date', desc: false }],
      searchQuery: '',
    });
    const parsed = parseDetailSearch(new URLSearchParams(search));
    expect(parsed.sorting).toEqual([{ id: 'complaint_date', desc: false }]);
    expect(parsed.searchQuery).toBe('');
    expect(parsed.pageIndex).toBe(0);
  });

  it('handles no sorting / no search (empty state) with sane defaults', () => {
    const search = buildDetailSearch({
      pageIndex: 0,
      pageSize: 50,
      sorting: [],
      searchQuery: '',
    });
    const parsed = parseDetailSearch(new URLSearchParams(search));
    expect(parsed.sorting).toEqual([]);
    expect(parsed.searchQuery).toBe('');
    expect(parsed.pageIndex).toBe(0);
    expect(parsed.pageSize).toBe(50);
    expect(parsed.filters).toEqual({});
  });

  it('drops empty extra filter values', () => {
    const search = buildDetailSearch(
      { pageIndex: 0, pageSize: 50, sorting: [], searchQuery: '' },
      { assigned_to: '', status: undefined, space_id: 'sp-1' },
    );
    const parsed = parseDetailSearch(new URLSearchParams(search));
    expect(parsed.filters.assigned_to).toBeUndefined();
    expect(parsed.filters.status).toBeUndefined();
    expect(parsed.filters.space_id).toBe('sp-1');
  });

  it('does not surface reserved keys (page/limit/sort/dir/query/id) as filters', () => {
    const sp = new URLSearchParams({
      page: '2',
      limit: '50',
      sort: 'status',
      dir: 'desc',
      query: 'abc',
      id: 'some-id',
      assigned_to: 'a1',
    });
    const parsed = parseDetailSearch(sp);
    expect(Object.keys(parsed.filters)).toEqual(['assigned_to']);
    expect(parsed.filters.id).toBeUndefined();
  });
});

/**
 * The menu and the cap are one decision.
 *
 * They were not: the menu offered 250, 500 and 1000 to every list while 34 of
 * the backend's list routes cap `limit` at 100 or 200, so picking one of the top
 * three sizes returned a 422 from the UI. The menu now stops where the narrowest
 * routes do, and a list whose route genuinely takes more passes its own `sizes`.
 */
describe('the page-size menu and the URL cap agree', () => {
  it('offers no size the URL parser would refuse', () => {
    for (const size of DEFAULT_PAGE_SIZES) {
      expect(size).toBeLessThanOrEqual(MAX_LIST_PAGE_SIZE);
    }
  });

  it('caps a hand-typed limit at the largest size the menu offers', () => {
    const parsed = parseDetailSearch(new URLSearchParams('limit=100000'));

    expect(parsed.pageSize).toBe(MAX_LIST_PAGE_SIZE);
    expect(parsed.pageSize).toBe(Math.max(...DEFAULT_PAGE_SIZES));
  });
});
