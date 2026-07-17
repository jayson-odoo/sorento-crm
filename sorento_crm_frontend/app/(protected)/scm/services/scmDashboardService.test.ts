import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import {
  EMPTY_SCM_FILTERS,
  getNetPosition,
  getProducts,
  getRollups,
  type ScmFilters,
} from './scmDashboardService';

function ok(body: unknown) {
  return { ok: true, json: async () => body } as unknown as Response;
}

/** Parse the URL passed to apiFetch on its Nth (default last) call. */
function calledUrl(idx = -1): URL {
  const calls = apiFetch.mock.calls;
  const raw = String(calls[idx < 0 ? calls.length + idx : idx][0]);
  // Absolute base is irrelevant — we only inspect path + query.
  return new URL(raw, 'http://x');
}

beforeEach(() => apiFetch.mockReset());

describe('scmDashboardService — contract param mapping', () => {
  it('net-position sends warehouse (comma-joined), health, and product search as query', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], empty: true, pagination: { total: 0, page: 1 } }));
    const filters: ScmFilters = {
      warehouses: ['WH-A', 'WH-B'],
      categoryId: 'cat-1',
      supplier: 'SUP-1',
      healthStatus: 'stockout',
      abcClass: null,
      xyzClass: null,
      productSearch: 'rebar',
      activeStatus: 'active',
      lifecycle: 'ongoing',
    };
    await getNetPosition({ ...filters, pageIndex: 2, pageSize: 25 });
    const u = calledUrl();
    expect(u.pathname).toBe('/api/v1/scm/dashboard/net-position');
    expect(u.searchParams.get('page')).toBe('3'); // 0-based → 1-based
    expect(u.searchParams.get('limit')).toBe('25');
    expect(u.searchParams.get('warehouse')).toBe('WH-A,WH-B');
    expect(u.searchParams.get('category_id')).toBe('cat-1');
    expect(u.searchParams.get('supplier')).toBe('SUP-1');
    expect(u.searchParams.get('health')).toBe('stockout');
    expect(u.searchParams.get('query')).toBe('rebar');
    // lifecycle scope is always sent so FE↔BE agree on the focused default
    expect(u.searchParams.get('active_status')).toBe('active');
    expect(u.searchParams.get('lifecycle')).toBe('ongoing');
    // never a repeatable `warehouses` alias — we send `warehouse`
    expect(u.searchParams.get('warehouses')).toBeNull();
  });

  it('net-position + rollups send the focused lifecycle default, and widening sends all', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], empty: true, pagination: { total: 0, page: 1 } }));
    // default (EMPTY) is the focused view → active + ongoing.
    await getNetPosition({ ...EMPTY_SCM_FILTERS, pageIndex: 0, pageSize: 50 });
    let u = calledUrl();
    expect(u.searchParams.get('active_status')).toBe('active');
    expect(u.searchParams.get('lifecycle')).toBe('ongoing');

    apiFetch.mockResolvedValue(ok({}));
    await getRollups({ ...EMPTY_SCM_FILTERS });
    u = calledUrl();
    expect(u.searchParams.get('active_status')).toBe('active');
    expect(u.searchParams.get('lifecycle')).toBe('ongoing');

    // "Show all" widens both — the query must reflect it.
    await getRollups({ ...EMPTY_SCM_FILTERS, activeStatus: 'all', lifecycle: 'all' });
    u = calledUrl();
    expect(u.searchParams.get('active_status')).toBe('all');
    expect(u.searchParams.get('lifecycle')).toBe('all');
  });

  it('net-position omits sort/dir when unsorted and warehouse when empty', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], empty: true, pagination: { total: 0, page: 1 } }));
    await getNetPosition({ ...EMPTY_SCM_FILTERS, pageIndex: 0, pageSize: 50 });
    const u = calledUrl();
    expect(u.searchParams.get('sort')).toBeNull();
    expect(u.searchParams.get('dir')).toBeNull();
    expect(u.searchParams.get('warehouse')).toBeNull();
  });

  it('net-position forwards explicit sort field + direction', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], empty: true, pagination: { total: 0, page: 1 } }));
    await getNetPosition({
      ...EMPTY_SCM_FILTERS,
      pageIndex: 0,
      pageSize: 25,
      sortField: 'net_position',
      sortDir: 'desc',
    });
    const u = calledUrl();
    expect(u.searchParams.get('sort')).toBe('net_position');
    expect(u.searchParams.get('dir')).toBe('desc');
  });

  it('products drill-down overrides warehouse scope and sets status', async () => {
    apiFetch.mockResolvedValue(ok({ data: [{ sku: 'X' }], total: 1, page: 1 }));
    const filters: ScmFilters = { ...EMPTY_SCM_FILTERS, warehouses: ['WH-A'] };
    const page = await getProducts(filters, { status: 'dead', warehouse: 'WH-B' });
    const u = calledUrl();
    expect(u.pathname).toBe('/api/v1/scm/dashboard/products');
    expect(u.searchParams.get('warehouse')).toBe('WH-B'); // popup scope wins
    expect(u.searchParams.get('status')).toBe('dead');
    expect(u.searchParams.get('page')).toBe('1'); // paginated envelope contract
    expect(u.searchParams.get('limit')).toBe('50');
    expect(page).toEqual({ data: [{ sku: 'X' }], total: 1, page: 1 });
  });

  it('rollups sends only the active filters', async () => {
    apiFetch.mockResolvedValue(ok({}));
    await getRollups({ ...EMPTY_SCM_FILTERS, supplier: 'SUP-9' });
    const u = calledUrl();
    expect(u.pathname).toBe('/api/v1/scm/dashboard/rollups');
    expect(u.searchParams.get('supplier')).toBe('SUP-9');
    expect(u.searchParams.get('warehouse')).toBeNull();
    expect(u.searchParams.get('health')).toBeNull();
  });

  it('throws an extracted message on a failed response', async () => {
    apiFetch.mockResolvedValue({
      ok: false,
      status: 403,
      headers: { get: () => 'application/json' },
      json: async () => ({ detail: 'Forbidden' }),
    } as unknown as Response);
    await expect(getRollups(EMPTY_SCM_FILTERS)).rejects.toThrow('Forbidden');
  });
});
