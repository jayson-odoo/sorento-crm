/**
 * Cost price uploads list query string (#1288, Lane A). The list is a DataGrid with a
 * sortable Code column and `manualSorting`, but the service built `page` / `limit` by hand
 * and never sent `sort` / `dir`, so clicking the Code header re-sorted nothing (the backend
 * list takes `sort` + `dir`, contract 1.3). PRINCIPLES.md layering: DataGrid query strings
 * come from `buildDataGridParams`, never a hand-built URLSearchParams.
 */
import { beforeEach, describe, it, expect, vi } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

import { getCostPriceChangeSets } from './costPriceService';
import { costPriceChangeSetsListQueryKey, costPriceChangeSetsPagerQuery } from '../hooks/useCostPriceChangeSets';

function lastQuery(): URLSearchParams {
  const url = String(apiFetch.mock.calls.at(-1)?.[0]);
  return new URLSearchParams(url.slice(url.indexOf('?') + 1));
}

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockResolvedValue(new Response(JSON.stringify({ data: [], total: 0, page: 1, limit: 50 }), { status: 200 }));
});

describe('getCostPriceChangeSets', () => {
  it('sends paging, the sort, the search and the filters', async () => {
    await getCostPriceChangeSets({
      pageIndex: 1,
      pageSize: 50,
      sorting: [{ id: 'code', desc: false }],
      searchQuery: 'TAI',
      status: ['draft', 'applied'],
      supplier_id: 'sup-1',
    });

    const q = lastQuery();
    expect(q.get('page')).toBe('2');
    expect(q.get('limit')).toBe('50');
    expect(q.get('sort')).toBe('code');
    expect(q.get('dir')).toBe('asc');
    expect(q.get('query')).toBe('TAI');
    expect(q.get('status')).toBe('draft,applied');
    expect(q.get('supplier_id')).toBe('sup-1');
  });

  it('leaves out what is not set', async () => {
    await getCostPriceChangeSets({ pageIndex: 0, pageSize: 50 });

    const q = lastQuery();
    expect([...q.keys()].sort()).toEqual(['limit', 'page']);
  });
});

describe('the detail pager follows the list sort', () => {
  it('passes the URL sort to the fetch and keys the cache by it', async () => {
    const params = {
      pageIndex: 0,
      pageSize: 50,
      sorting: [{ id: 'code', desc: true }],
      searchQuery: '',
      filters: {},
    };
    await costPriceChangeSetsPagerQuery.fetchPage(params);

    expect(lastQuery().get('sort')).toBe('code');
    expect(lastQuery().get('dir')).toBe('desc');
    expect(costPriceChangeSetsPagerQuery.listQueryKey(params)).not.toEqual(
      costPriceChangeSetsPagerQuery.listQueryKey({ ...params, sorting: [{ id: 'code', desc: false }] }),
    );
    expect(costPriceChangeSetsListQueryKey({ pageIndex: 0, pageSize: 50, sorting: [{ id: 'code', desc: true }] })).toContainEqual(
      [{ id: 'code', desc: true }],
    );
  });
});
