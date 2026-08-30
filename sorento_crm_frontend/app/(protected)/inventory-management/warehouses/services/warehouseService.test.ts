/**
 * Warehouses feature service - the `fulfilment_planning` contract (borrow ladder v7.1 S1,
 * migration 443; AC-S1-3).
 *
 * The column is NOT NULL from 443, which ships in this same change, so the service reads
 * and writes the field straight through - no normalisation, because a coalesce here would
 * write `Off` over a real value the day the field were ever dropped from a response, and
 * hide it. What is pinned instead is the wiring: the flag survives every read, a PUT
 * carrying it reaches the backend, and the list column's sort key reaches the query string.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import {
  getWarehouses,
  getWarehouse,
  createWarehouse,
  updateWarehouse,
} from './warehouseService';

function ok(body: unknown) {
  return { ok: true, json: async () => body } as unknown as Response;
}

const WAREHOUSE = {
  id: '11111111-1111-4111-8111-111111111111',
  warehouse_code: 'WH-CUR',
  warehouse_name: 'Main Store',
  is_active: true,
  counts_as_available: true,
  fulfilment_planning: true,
};

const OFF_PLAN = { ...WAREHOUSE, fulfilment_planning: false };

beforeEach(() => {
  apiFetch.mockReset();
});

describe('the fulfilment-planning flag travels through every read', () => {
  it('a list row keeps the flag the backend states', async () => {
    apiFetch.mockResolvedValue(
      ok({
        data: [WAREHOUSE, OFF_PLAN],
        pagination: { page: 1, limit: 10, total: 2, total_pages: 1 },
      }),
    );
    const page = await getWarehouses({ pageIndex: 0, pageSize: 10, sorting: [], searchQuery: '' });
    expect(page.data.map((row) => row.fulfilment_planning)).toEqual([true, false]);
  });

  it('a single warehouse keeps it', async () => {
    apiFetch.mockResolvedValue(ok(OFF_PLAN));
    expect((await getWarehouse(OFF_PLAN.id)).fulfilment_planning).toBe(false);
  });

  it('the create response keeps it', async () => {
    apiFetch.mockResolvedValue(ok(WAREHOUSE));
    const created = await createWarehouse({ warehouse_code: 'WH-NEW', is_active: true });
    expect(created.fulfilment_planning).toBe(true);
  });

  it('the update response keeps it, so the list refreshes without a reload', async () => {
    apiFetch.mockResolvedValue(ok(WAREHOUSE));
    const saved = await updateWarehouse(WAREHOUSE.id, { fulfilment_planning: true });
    expect(saved.fulfilment_planning).toBe(true);
  });

  it('a PUT carrying the flag sends it through to the backend', async () => {
    apiFetch.mockResolvedValue(ok(WAREHOUSE));
    await updateWarehouse(WAREHOUSE.id, { fulfilment_planning: true });
    const [url, init] = apiFetch.mock.calls[0];
    expect(String(url)).toBe(`/api/v1/inventory/warehouses/${WAREHOUSE.id}`);
    expect((init as RequestInit).method).toBe('PUT');
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ fulfilment_planning: true });
  });

  it('`sort=fulfilment_planning` reaches the query string the list column offers', async () => {
    apiFetch.mockResolvedValue(
      ok({ data: [], pagination: { page: 1, limit: 10, total: 0, total_pages: 0 } }),
    );
    await getWarehouses({
      pageIndex: 0,
      pageSize: 10,
      sorting: [{ id: 'fulfilment_planning', desc: true }],
      searchQuery: '',
    });
    const url = new URL(String(apiFetch.mock.calls[0][0]), 'http://x');
    expect(url.searchParams.get('sort')).toBe('fulfilment_planning');
    expect(url.searchParams.get('dir')).toBe('desc');
  });
});
