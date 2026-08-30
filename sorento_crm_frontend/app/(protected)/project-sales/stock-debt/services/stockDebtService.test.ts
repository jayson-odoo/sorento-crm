/**
 * S2 - stockDebtService, against the contract in its own header.
 *
 * Pins the two paths, the params the board sends (through `buildDataGridParams`, never a
 * hand-built query string), and that a failure surfaces the SERVER's message - which is what
 * the page's error state renders beside its Retry (AC-S2-12).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import { getStockDebtCell, getStockDebtList } from './stockDebtService';

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

const EMPTY = {
  data: [],
  pagination: { total: 0, page: 1, limit: 25 },
  months: [],
  tba_month: '2029-01',
  groups: [],
};

beforeEach(() => vi.clearAllMocks());

describe('getStockDebtList', () => {
  it('sends the page, the needle, the group and the debt switch', async () => {
    mockedFetch.mockResolvedValue(okResponse(EMPTY));

    await getStockDebtList({
      pageIndex: 2,
      pageSize: 25,
      query: 'SRTWB',
      group: 'BB',
      onlyDebt: true,
    });

    const url = calledUrl();
    expect(url.pathname).toBe('/api/v1/project-sales/stock-debt');
    // 1-based on the wire: `buildDataGridParams` owns that translation, here and everywhere.
    expect(url.searchParams.get('page')).toBe('3');
    expect(url.searchParams.get('limit')).toBe('25');
    expect(url.searchParams.get('query')).toBe('SRTWB');
    expect(url.searchParams.get('group')).toBe('BB');
    expect(url.searchParams.get('only_debt')).toBe('true');
  });

  it('drops an empty group and still states only_debt=false', async () => {
    mockedFetch.mockResolvedValue(okResponse(EMPTY));

    await getStockDebtList({
      pageIndex: 0,
      pageSize: 50,
      query: '',
      group: '',
      onlyDebt: false,
    });

    const url = calledUrl();
    expect(url.searchParams.get('group')).toBeNull();
    expect(url.searchParams.get('query')).toBeNull();
    // Not dropped: `false` is the answer, and an omitted flag would default back to true.
    expect(url.searchParams.get('only_debt')).toBe('false');
  });

  it('returns the envelope as the backend states it', async () => {
    const body = {
      ...EMPTY,
      months: ['2026-08', '2026-09'],
      groups: ['BB', 'IB'],
      pagination: { total: 1, page: 1, limit: 25 },
      data: [
        {
          product_id: 'p1',
          product_code: 'SRTWB242',
          product_name: 'Basin',
          months: [
            { key: '2026-08', balance: 55, tone: 'green' },
            { key: '2026-09', balance: -16, tone: 'red' },
          ],
          tba: -100,
          undated: 0,
          unlocated: -12,
        },
      ],
    };
    mockedFetch.mockResolvedValue(okResponse(body));

    await expect(
      getStockDebtList({
        pageIndex: 0,
        pageSize: 25,
        query: '',
        group: '',
        onlyDebt: true,
      }),
    ).resolves.toEqual(body);
  });

  it('surfaces the server message', async () => {
    mockedFetch.mockResolvedValue(failure('Stock debt is unavailable'));

    await expect(
      getStockDebtList({
        pageIndex: 0,
        pageSize: 25,
        query: '',
        group: '',
        onlyDebt: true,
      }),
    ).rejects.toThrow('Stock debt is unavailable');
  });
});

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
