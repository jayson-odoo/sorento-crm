/**
 * AC-FE-01 (`PLAN-oi-header-list-detail.md`, W): the header list's own params builder -
 * `state`/`sort`/`dir`/`query`/`raised_by`/`agent`/`project_id` must map onto the exact
 * query string the backend contract names (the plan's own "Contract" section), and the
 * values `OrderInquiryHeadersList` sends on first render (`state=outstanding`,
 * `sort=raised_at`, `dir=asc`) must survive unchanged. `buildDataGridParams` is kept
 * REAL here (not mocked) - the whole point is pinning what it actually produces, not
 * what a stub says it produces.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

const { apiFetch } = await import('@/lib/api');
const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

import { listOrderInquiryHeaders } from './orderInquiryService';

function ok(body: unknown) {
  return { ok: true, json: async () => body } as unknown as Response;
}

function calledUrl(): URL {
  const url = mockFetch.mock.calls[0][0] as string;
  return new URL(url, 'http://test.local');
}

beforeEach(() => mockFetch.mockReset());

describe('listOrderInquiryHeaders params builder (AC-LS contract)', () => {
  it('maps state/sort/dir/query/filters onto the exact query string the backend names', async () => {
    mockFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 2, limit: 10 } }));

    await listOrderInquiryHeaders({
      state: 'completed',
      query: 'CB6633',
      raised_by: 'user-1',
      agent: 'Sean',
      project_id: 'proj-1',
      sort: 'customer',
      dir: 'desc',
      page: 2,
      limit: 10,
    });

    const search = calledUrl().searchParams;
    expect(search.get('state')).toBe('completed');
    expect(search.get('query')).toBe('CB6633');
    expect(search.get('raised_by')).toBe('user-1');
    expect(search.get('agent')).toBe('Sean');
    expect(search.get('project_id')).toBe('proj-1');
    expect(search.get('sort')).toBe('customer');
    expect(search.get('dir')).toBe('desc');
    expect(search.get('page')).toBe('2');
    expect(search.get('limit')).toBe('10');
  });

  it('omits a filter that was not given, rather than sending it empty', async () => {
    mockFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 1, limit: 25 } }));

    await listOrderInquiryHeaders({ state: 'all' });

    const search = calledUrl().searchParams;
    expect(search.get('state')).toBe('all');
    expect(search.has('raised_by')).toBe(false);
    expect(search.has('agent')).toBe(false);
    expect(search.has('project_id')).toBe(false);
  });

  it('defaults to state=outstanding, sort=raised_at, dir=asc - what the list sends on first render', async () => {
    mockFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 1, limit: 25 } }));

    // `OrderInquiryHeadersList`'s own `params` useMemo always sends these three
    // explicitly (its `DEFAULT_SORTING`/`stateFilter` initial values) - this pins that
    // shape survives the params builder unchanged.
    await listOrderInquiryHeaders({ state: 'outstanding', sort: 'raised_at', dir: 'asc' });

    const search = calledUrl().searchParams;
    expect(search.get('state')).toBe('outstanding');
    expect(search.get('sort')).toBe('raised_at');
    expect(search.get('dir')).toBe('asc');
    expect(search.get('page')).toBe('1');
    expect(search.get('limit')).toBe('25');
  });
});
