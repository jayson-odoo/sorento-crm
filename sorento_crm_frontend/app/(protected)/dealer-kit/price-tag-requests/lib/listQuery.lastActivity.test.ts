/**
 * FORMS-LAST-ACTIVITY review fix: the price tag pager rebuilds the list's Last activity range from the
 * record URL, and walks last activity newest first when the URL names no sort (the list's own default).
 */
import { describe, it, expect } from 'vitest';
import type { ListPagerParams } from '@/hooks/useListPager';
import { priceTagRequestsListParamsFromUrl } from './listQuery';

const base: ListPagerParams = { pageIndex: 0, pageSize: 50, sorting: [], searchQuery: '', filters: {} };

describe('price tag pager list query - Last activity', () => {
  it('reads the range back from the record URL filters', () => {
    const params = priceTagRequestsListParamsFromUrl({
      ...base,
      filters: { last_activity_from: '2026-03-11', last_activity_to: '2026-03-12' },
    });
    expect(params.last_activity_from).toBe('2026-03-11');
    expect(params.last_activity_to).toBe('2026-03-12');
  });

  it('defaults to last_activity_at newest first when the URL has no sort', () => {
    const params = priceTagRequestsListParamsFromUrl(base);
    expect(params.sort).toBe('last_activity_at');
    expect(params.dir).toBe('desc');
  });

  it('keeps an explicit sort from the URL', () => {
    const params = priceTagRequestsListParamsFromUrl({ ...base, sorting: [{ id: 'doc_number', desc: false }] });
    expect(params.sort).toBe('doc_number');
    expect(params.dir).toBe('asc');
  });
});
