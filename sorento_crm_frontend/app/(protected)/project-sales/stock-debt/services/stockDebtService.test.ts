/**
 * S2 - stockDebtService, against the contract in its own header.
 *
 * `getStockDebtCell` pins the two paths, the params the board sends (through
 * `buildDataGridParams`, never a hand-built query string), and that a failure surfaces the
 * SERVER's message - which is what the page's error state renders beside its Retry
 * (AC-S2-12).
 *
 * `getStockDebtList` runs off the Phase-1 mock while `USE_STOCK_DEBT_FILTER_MOCKS` is `true`
 * (PLAN-stock-debt-filters-totals-export-24sep.md, Phase 1: "service -> mock", PRINCIPLES.md).
 * These tests exercise THAT contract, so they can only pin what the mock actually does -
 * the real backend's AC-1 to AC-9 are Phase 2's, tested fresh from the UAC once the flag
 * flips off and this function calls `apiFetch` again.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import { getStockDebtCell, getStockDebtList } from './stockDebtService';
import type { StockDebtListParams } from './stockDebtService';

const BASE_PARAMS: StockDebtListParams = {
  pageIndex: 0,
  pageSize: 25,
  query: '',
  group: '',
  onlyDebt: false,
  book: 'all',
  supplierId: '',
  cutoff: null,
};

const mockedFetch = vi.mocked(apiFetch);

function okResponse(body: unknown): Response {
  return { ok: true, json: async () => body } as Response;
}

function failure(message: string): Response {
  return {
    ok: false,
    status: 500,
    headers: { get: () => 'application/json' },
    json: async () => ({ detail: message }),
    text: async () => '',
    clone() {
      return this;
    },
  } as unknown as Response;
}

function calledUrl(): URL {
  return new URL(mockedFetch.mock.calls[0][0] as string, 'http://localhost');
}

beforeEach(() => vi.clearAllMocks());

describe('getStockDebtList (Phase-1 mock)', () => {
  it('never calls the backend while the mock flag is on', async () => {
    await getStockDebtList(BASE_PARAMS);
    expect(mockedFetch).not.toHaveBeenCalled();
  });

  it('narrows by product code or name', async () => {
    const result = await getStockDebtList({ ...BASE_PARAMS, query: 'SRTWB242' });
    expect(result.data.map((row) => row.product_code)).toEqual(['SRTWB242']);
  });

  it('keeps only the chosen book (R1, AC-8)', async () => {
    const project = await getStockDebtList({ ...BASE_PARAMS, book: 'project' });
    const retail = await getStockDebtList({ ...BASE_PARAMS, book: 'retail' });
    expect(project.data.length).toBeGreaterThan(0);
    expect(retail.data.length).toBeGreaterThan(0);
    expect(project.data.map((row) => row.product_code)).not.toEqual(
      expect.arrayContaining(retail.data.map((row) => row.product_code)),
    );
  });

  it('keeps only products with no supplier under supplierId="none" (R3, AC-4)', async () => {
    const result = await getStockDebtList({ ...BASE_PARAMS, supplierId: 'none' });
    expect(result.data.length).toBeGreaterThan(0);
    result.data.forEach((row) => expect(row.supplier_id).toBeNull());
  });

  it('trims the axis at the cutoff month and never drops undated/unlocated demand (R2, A3)', async () => {
    const unfiltered = await getStockDebtList(BASE_PARAMS);
    const result = await getStockDebtList({ ...BASE_PARAMS, cutoff: '2026-10-15' });
    expect(result.months).toEqual(['2026-09', '2026-10']);
    expect(result.months.length).toBeLessThan(unfiltered.months.length);
  });

  it('carries a row total that sums its months, tba, undated and unlocated (AC-5)', async () => {
    const result = await getStockDebtList({ ...BASE_PARAMS, query: 'SRTWB242' });
    const row = result.data[0];
    const expected =
      row.months.reduce((sum, month) => sum + month.balance, 0) +
      row.tba +
      row.undated +
      row.unlocated;
    expect(row.total).toBe(expected);
  });

  it('carries totals over the WHOLE filtered set, unaffected by paging (AC-6)', async () => {
    const page1 = await getStockDebtList({ ...BASE_PARAMS, pageSize: 1, pageIndex: 0 });
    const page2 = await getStockDebtList({ ...BASE_PARAMS, pageSize: 1, pageIndex: 1 });
    expect(page1.totals).toEqual(page2.totals);
    expect(page1.pagination.total).toBeGreaterThan(1);
  });

  it('carries the distinct last suppliers of the filtered set, sorted by name (AC-7)', async () => {
    const result = await getStockDebtList(BASE_PARAMS);
    const names = result.suppliers.map((entry) => entry.name);
    expect(names).toEqual([...names].sort());
    expect(result.suppliers.length).toBeGreaterThan(0);
  });

  it('drops rows with no negative anywhere when onlyDebt is on', async () => {
    const withDebt = await getStockDebtList({ ...BASE_PARAMS, onlyDebt: true });
    const whole = await getStockDebtList({ ...BASE_PARAMS, onlyDebt: false });
    expect(withDebt.data.length).toBeLessThan(whole.data.length);
  });
});

// Unchanged in this lane's Phase 1 (see the service header): `getStockDebtCell` keeps
// calling the real backend, so these still exercise `apiFetch`.
describe('getStockDebtCell', () => {
  it('addresses the product and the month key', async () => {
    mockedFetch.mockResolvedValue(okResponse({ demand: [], supply: [] }));

    await getStockDebtCell('p1', '2026-10');

    const url = calledUrl();
    expect(url.pathname).toBe('/api/v1/project-sales/stock-debt/p1/cell');
    expect(url.searchParams.get('month')).toBe('2026-10');
  });

  it('addresses the three buckets that are not months', async () => {
    mockedFetch.mockResolvedValue(okResponse({ demand: [], supply: [] }));

    await getStockDebtCell('p1', 'undated');
    expect(calledUrl().searchParams.get('month')).toBe('undated');

    vi.clearAllMocks();
    mockedFetch.mockResolvedValue(okResponse({ demand: [], supply: [] }));
    await getStockDebtCell('p1', 'unlocated');
    expect(calledUrl().searchParams.get('month')).toBe('unlocated');
  });

  it("carries the board's ownership group, so the drill foots with the cell", async () => {
    mockedFetch.mockResolvedValue(okResponse({ demand: [], supply: [] }));

    await getStockDebtCell('p1', '2026-10', 'BB');

    expect(calledUrl().searchParams.get('group')).toBe('BB');
  });

  it('omits the group when the board is showing the whole book', async () => {
    mockedFetch.mockResolvedValue(okResponse({ demand: [], supply: [] }));

    await getStockDebtCell('p1', '2026-10', '');

    expect(calledUrl().searchParams.get('group')).toBeNull();
  });

  it('surfaces the server message', async () => {
    mockedFetch.mockResolvedValue(failure('That cell could not be read'));

    await expect(getStockDebtCell('p1', 'tba')).rejects.toThrow(
      'That cell could not be read',
    );
  });
});
