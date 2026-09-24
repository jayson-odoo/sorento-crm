/**
 * stockDebtService - the REAL (Phase 2) backend contract, from the PHASE-2 BACKEND
 * CONTRACT header of `stockDebtService.ts` (PLAN-stock-debt-filters-totals-export-24sep.md,
 * AC-1 to AC-18).
 *
 * `stockDebtService.test.ts` already pins the Phase-1 MOCK branch (`USE_STOCK_DEBT_FILTER_
 * MOCKS === true` today) - including that it never touches the network. This file pins the
 * branch the header says Phase 2 ships: "Phase 2 flips the flag to `false` and deletes the
 * mock branch - a one-line swap ... not a rewrite of its callers." `USE_STOCK_DEBT_FILTER_
 * MOCKS` is declared LOCALLY in `stockDebtService.ts` (not a separate mock-store module the
 * way `coverageService.ts` / `USE_COVERAGE_MOCKS` is), so there is no live binding to flip
 * from outside it - these tests call the exported functions exactly as a real caller would
 * and assert the request `apiFetch` receives. RED today because the mock branch intercepts
 * before `apiFetch` is ever called (`getStockDebtList` / `exportStockDebt`) or because the
 * function does not yet accept the new params at all (`getStockDebtCell`); GREEN once the
 * mock branch is deleted and the params are wired through, with no change needed here.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import {
  exportStockDebt,
  getStockDebtCell,
  getStockDebtList,
} from './stockDebtService';
import type { StockDebtExportParams, StockDebtListParams } from './stockDebtService';

const mockedFetch = vi.mocked(apiFetch);

const LIST_PARAMS: StockDebtListParams = {
  pageIndex: 0,
  pageSize: 25,
  query: 'SRTWB242',
  group: 'BB',
  onlyDebt: true,
  book: 'retail',
  supplierId: 'sup-guangdong',
  cutoff: '2026-11-30',
};

const EXPORT_PARAMS: StockDebtExportParams = {
  query: 'SRTWB242',
  group: 'BB',
  onlyDebt: true,
  book: 'retail',
  supplierId: 'sup-guangdong',
  cutoff: '2026-11-30',
  split: 'supplier',
};

function ok(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: async () => body,
  } as unknown as Response;
}

function calledUrl(callIndex = 0): URL {
  const call = mockedFetch.mock.calls[callIndex];
  return new URL(call[0] as string, 'http://localhost');
}

beforeEach(() => vi.clearAllMocks());

describe('getStockDebtList - real backend (AC-1 to AC-9)', () => {
  it('calls apiFetch (not the Phase-1 mock) at all', async () => {
    mockedFetch.mockResolvedValue(
      ok({
        data: [], pagination: { total: 0, page: 1, limit: 25 }, months: [],
        tba_month: '2029-01', groups: [], totals: { months: {}, tba: 0, undated: 0, unlocated: 0, total: 0 },
        suppliers: [], sheet_counts: { supplier: 0, category: 0, supplier_category: 0 },
      }),
    );
    await getStockDebtList(LIST_PARAMS);
    expect(mockedFetch).toHaveBeenCalledTimes(1);
  });

  it('sends group, only_debt, book, supplier_id and cutoff on the query string', async () => {
    mockedFetch.mockResolvedValue(
      ok({
        data: [], pagination: { total: 0, page: 1, limit: 25 }, months: [],
        tba_month: '2029-01', groups: [], totals: { months: {}, tba: 0, undated: 0, unlocated: 0, total: 0 },
        suppliers: [], sheet_counts: { supplier: 0, category: 0, supplier_category: 0 },
      }),
    );
    await getStockDebtList(LIST_PARAMS);

    const url = calledUrl();
    expect(url.pathname).toBe('/api/v1/project-sales/stock-debt');
    expect(url.searchParams.get('query')).toBe('SRTWB242');
    expect(url.searchParams.get('group')).toBe('BB');
    expect(url.searchParams.get('only_debt')).toBe('true');
    expect(url.searchParams.get('book')).toBe('retail');
    expect(url.searchParams.get('supplier_id')).toBe('sup-guangdong');
    expect(url.searchParams.get('cutoff')).toBe('2026-11-30');
  });

  it('omits book from the query when it is "all" (the default, per the header)', async () => {
    mockedFetch.mockResolvedValue(
      ok({
        data: [], pagination: { total: 0, page: 1, limit: 25 }, months: [],
        tba_month: '2029-01', groups: [], totals: { months: {}, tba: 0, undated: 0, unlocated: 0, total: 0 },
        suppliers: [], sheet_counts: { supplier: 0, category: 0, supplier_category: 0 },
      }),
    );
    await getStockDebtList({ ...LIST_PARAMS, book: 'all' });
    const url = calledUrl();
    expect(url.searchParams.get('book')).toBeFalsy();
  });

  it('surfaces the server error message on a non-ok response', async () => {
    mockedFetch.mockResolvedValue({
      ok: false,
      status: 500,
      headers: { get: () => 'application/json' },
      json: async () => ({ detail: 'stock debt boom' }),
      text: async () => JSON.stringify({ detail: 'stock debt boom' }),
      clone() {
        return this;
      },
    } as unknown as Response);
    await expect(getStockDebtList(LIST_PARAMS)).rejects.toThrow(/stock debt boom/);
  });
});

describe('getStockDebtCell - real backend (AC-11)', () => {
  it('passes cutoff and book alongside group and month', async () => {
    mockedFetch.mockResolvedValue(ok({ demand: [], supply: [] }));

    // AC-11: the drill foots with the cell that opened it, so it must be able to carry the
    // SAME cutoff/book the board was narrowed to. The exact JS call shape is not fixed by
    // the contract header (only the wire params are) - this assumes the coder extends the
    // existing positional signature `(productId, month, group?)` with two more optional
    // positional args, `cutoff?` then `book?`, consistent with how `group` was added.
    await (
      getStockDebtCell as unknown as (
        productId: string,
        month: string,
        group?: string,
        cutoff?: string,
        book?: string,
      ) => Promise<unknown>
    )('prod-1', '2026-11', 'BB', '2026-11-30', 'retail');

    const url = calledUrl();
    expect(url.pathname).toBe('/api/v1/project-sales/stock-debt/prod-1/cell');
    expect(url.searchParams.get('month')).toBe('2026-11');
    expect(url.searchParams.get('group')).toBe('BB');
    expect(url.searchParams.get('cutoff')).toBe('2026-11-30');
    expect(url.searchParams.get('book')).toBe('retail');
  });
});

describe('exportStockDebt - real backend (AC-12 to AC-18)', () => {
  it('POSTs the filters and split to /stock-debt/export and returns the download row', async () => {
    const download = {
      id: 'dl-1', kind: 'stock_debt_xlsx', status: 'pending',
      filename: 'stock-debt-24092026.xlsx', created_at: '2026-09-24T00:00:00Z', ready_at: null,
    };
    mockedFetch.mockResolvedValue(ok(download));

    const result = await exportStockDebt(EXPORT_PARAMS);

    expect(mockedFetch).toHaveBeenCalledTimes(1);
    const [url, init] = mockedFetch.mock.calls[0];
    expect(url).toBe('/api/v1/project-sales/stock-debt/export');
    expect((init as RequestInit).method).toBe('POST');
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body).toMatchObject({
      query: 'SRTWB242',
      group: 'BB',
      only_debt: true,
      book: 'retail',
      supplier_id: 'sup-guangdong',
      cutoff: '2026-11-30',
      split: 'supplier',
    });
    expect(result).toEqual(download);
  });

  it('surfaces the server error message on a non-ok response, and no row lingers', async () => {
    mockedFetch.mockResolvedValue({
      ok: false,
      status: 422,
      headers: { get: () => 'application/json' },
      json: async () => ({ detail: 'Narrow the plan first' }),
      text: async () => JSON.stringify({ detail: 'Narrow the plan first' }),
      clone() {
        return this;
      },
    } as unknown as Response);
    await expect(exportStockDebt(EXPORT_PARAMS)).rejects.toThrow(/Narrow the plan first/);
  });
});
