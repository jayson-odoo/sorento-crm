/** #1356: the branches list request carries the list state and the filters the API reads. */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

import { getBranches } from './branchService';

function ok(body: unknown) {
  return { ok: true, json: () => Promise.resolve(body) } as unknown as Response;
}

beforeEach(() => apiFetch.mockReset());

describe('getBranches', () => {
  it('sends page, sort, search, book and in_crm', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 1, limit: 50 } }));
    await getBranches({
      pageIndex: 1,
      pageSize: 50,
      sorting: [{ id: 'branch_code', desc: false }],
      searchQuery: 'kl',
      book: 'SRT',
      inCrm: 'no',
    });
    const url = new URL(apiFetch.mock.calls[0][0], 'http://x');
    expect(url.pathname).toBe('/api/v1/order-management/branches');
    expect(Object.fromEntries(url.searchParams)).toEqual({
      page: '2',
      limit: '50',
      sort: 'branch_code',
      dir: 'asc',
      query: 'kl',
      book: 'SRT',
      in_crm: 'false',
    });
  });

  it('sends customer_id for the customer tab and omits unset filters', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 1, limit: 20 } }));
    await getBranches({ pageIndex: 0, pageSize: 20, sorting: [], searchQuery: '', customerId: 'c-1' });
    const url = new URL(apiFetch.mock.calls[0][0], 'http://x');
    expect(url.searchParams.get('customer_id')).toBe('c-1');
    expect(url.searchParams.has('in_crm')).toBe(false);
    expect(url.searchParams.has('book')).toBe(false);
  });
});
