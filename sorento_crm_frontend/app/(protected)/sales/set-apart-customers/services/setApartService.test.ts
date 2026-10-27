/**
 * setApartService: paths, methods, bodies and query params are asserted directly (a key typo
 * is a silently dropped field on the backend, not an error).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', () => ({ apiFetch }));

import {
  createSetApart,
  getSetApartCustomerOptions,
  getSetApartCustomers,
  updateSetApart,
} from './setApartService';

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

beforeEach(() => apiFetch.mockReset());

describe('setApartService', () => {
  it('lists with page, limit, sort, dir and query through buildDataGridParams', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 1, limit: 50 } }));
    await getSetApartCustomers({
      pageIndex: 1,
      pageSize: 50,
      sorting: [{ id: 'customer_name', desc: true }],
      searchQuery: 'bravat',
    });
    const url = new URL(apiFetch.mock.calls[0][0], 'http://x');
    expect(url.pathname).toBe('/api/v1/sales/set-apart-customers');
    expect(Object.fromEntries(url.searchParams)).toEqual({
      page: '2',
      limit: '50',
      sort: 'customer_name',
      dir: 'desc',
      query: 'bravat',
    });
  });

  it('reads the customer options with the typed query', async () => {
    apiFetch.mockResolvedValue(ok({ data: [{ value: 'c1', label: 'A001 - Acme' }] }));
    const options = await getSetApartCustomerOptions('acm');
    expect(apiFetch.mock.calls[0][0]).toBe('/api/v1/sales/set-apart-customers/customer-options?query=acm');
    expect(options).toEqual([{ value: 'c1', label: 'A001 - Acme' }]);
  });

  it('creates with a POST carrying the null To month', async () => {
    apiFetch.mockResolvedValue(ok({ id: 'r1' }));
    await createSetApart({ customer_id: 'c1', from_month: '2026-01', to_month: null });
    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toBe('/api/v1/sales/set-apart-customers');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ customer_id: 'c1', from_month: '2026-01', to_month: null });
  });

  it('edits with a PATCH on the row', async () => {
    apiFetch.mockResolvedValue(ok({ id: 'r1' }));
    await updateSetApart('r1', { customer_id: 'c1', from_month: '2026-01', to_month: '2026-06' });
    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toBe('/api/v1/sales/set-apart-customers/r1');
    expect(init.method).toBe('PATCH');
    expect(JSON.parse(init.body).to_month).toBe('2026-06');
  });

  it('throws the backend message on a refusal', async () => {
    apiFetch.mockResolvedValue({
      ok: false,
      status: 422,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ message: 'These months overlap another row', code: 'set_apart_overlap' }),
      text: async () => '',
    } as unknown as Response);
    await expect(
      createSetApart({ customer_id: 'c1', from_month: '2026-01', to_month: null }),
    ).rejects.toThrow(/overlap/);
  });
});
