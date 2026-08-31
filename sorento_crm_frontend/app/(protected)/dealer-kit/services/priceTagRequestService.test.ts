/**
 * The CRM price tag list asks the SERVER for its page.
 *
 * It used to fetch the whole table on every keystroke and every page turn and
 * cut the page out in the browser, so the record count under the grid was the
 * length of whatever array had arrived rather than what the table holds, and a
 * queue of any size shipped in full to each reader. The query string is built
 * by `buildDataGridParams`, which is the one place page/limit/sort/dir/query
 * are spelled.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import { listPriceTagRequests } from './priceTagRequestService';

const mockFetch = vi.mocked(apiFetch);

function page(data: unknown[], total: number) {
  return {
    ok: true,
    json: async () => ({ data, pagination: { total, page: 2, limit: 25 } }),
  } as never;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('listPriceTagRequests', () => {
  it('sends the page, the size, the sort and the search to the server', async () => {
    mockFetch.mockResolvedValue(page([], 0));

    await listPriceTagRequests({
      page: 2,
      limit: 25,
      sort: 'doc_number',
      dir: 'desc',
      query: 'PT-2026',
      status: 'new',
    });

    const url = new URL(mockFetch.mock.calls[0][0] as string, 'http://test.invalid');
    expect(url.searchParams.get('page')).toBe('2');
    expect(url.searchParams.get('limit')).toBe('25');
    expect(url.searchParams.get('sort')).toBe('doc_number');
    expect(url.searchParams.get('dir')).toBe('desc');
    expect(url.searchParams.get('query')).toBe('PT-2026');
    expect(url.searchParams.get('status')).toBe('new');
  });

  it('answers with the page the server sent and the TOTAL it counted', async () => {
    // 3 rows on the page, 87 in the table. Paging in the browser could only ever
    // have said 3.
    mockFetch.mockResolvedValue(page([{ id: 'a' }, { id: 'b' }, { id: 'c' }], 87));

    const result = await listPriceTagRequests({ page: 2, limit: 25 });

    expect(result.data).toHaveLength(3);
    expect(result.pagination.total).toBe(87);
  });

  it('does not re-sort or re-slice what the server already ordered', async () => {
    mockFetch.mockResolvedValue(page([{ id: 'b' }, { id: 'a' }], 2));

    const result = await listPriceTagRequests({
      page: 1,
      limit: 1,
      sort: 'doc_number',
      dir: 'asc',
    });

    expect(result.data.map((row) => row.id)).toEqual(['b', 'a']);
  });
});
