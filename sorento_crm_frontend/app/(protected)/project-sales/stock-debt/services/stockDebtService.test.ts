/**
 * S2 - stockDebtService, against the contract in its own header.
 *
 * Pins the `getStockDebtCell` paths, the params the board sends (through
 * `buildDataGridParams`, never a hand-built query string), and that a failure surfaces the
 * SERVER's message - which is what the page's error state renders beside its Retry
 * (AC-S2-12).
 *
 * `getStockDebtList`'s own Phase-1-mock suite that used to live here is retired: Phase 2
 * flipped `USE_STOCK_DEBT_FILTER_MOCKS` to `false` and deleted the mock branch, so
 * `stockDebtService.real.test.ts` is the one pinning the AC-1 to AC-18 wire contract now
 * (PLAN-stock-debt-filters-totals-export-24sep.md).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import { getStockDebtCell } from './stockDebtService';

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
