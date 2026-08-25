/**
 * stockVisibilityService - the service boundary the card was built against
 * (PLAN-stock-visibility-policy, S4).
 *
 * The component test mocks THIS module, so the URL, verb and body each function
 * actually sends is only proven here. `apiFetch` is the seam; `extractApiError` is
 * real, because the message it produces is what the card toasts.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', () => ({ apiFetch }));

import {
  deleteStockVisibility,
  getDealerPoolWarehouses,
  getStockVisibility,
  saveStockVisibility,
  searchStockVisibilityWarehouses,
  stockVisibilityScopePath,
} from './stockVisibilityService';

function jsonResponse(body: unknown, init: { ok?: boolean; status?: number } = {}): Response {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    headers: new Headers({ 'content-type': 'application/json' }),
    async json() {
      return body;
    },
    async text() {
      return JSON.stringify(body);
    },
  } as unknown as Response;
}

const POLICY = {
  mode: 'compact',
  warehouses: [{ id: 'wh-1', code: 'BRW', name: 'Rawang Main Warehouse' }],
  hide_zero_locations: true,
  source: 'contact',
  source_label: null,
};

function lastCall(): [string, RequestInit | undefined] {
  return apiFetch.mock.calls[apiFetch.mock.calls.length - 1] as [string, RequestInit | undefined];
}

function queryOf(url: string): URLSearchParams {
  return new URLSearchParams(url.split('?')[1] ?? '');
}

beforeEach(() => {
  apiFetch.mockReset();
});

describe('one path per tier', () => {
  it('maps each scope to its route segment', () => {
    expect(stockVisibilityScopePath({ kind: 'contact', contactId: 'c-1' })).toBe(
      '/api/v1/inventory/stock-visibility/contacts/c-1',
    );
    expect(stockVisibilityScopePath({ kind: 'access_type', accessTypeCode: 'dealer' })).toBe(
      '/api/v1/inventory/stock-visibility/access-types/dealer',
    );
    expect(stockVisibilityScopePath({ kind: 'default' })).toBe(
      '/api/v1/inventory/stock-visibility/default',
    );
  });

  it('reads the tier with a GET', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ effective: POLICY, override: POLICY }));
    const res = await getStockVisibility({ kind: 'contact', contactId: 'c-1' });
    expect(lastCall()[0]).toBe('/api/v1/inventory/stock-visibility/contacts/c-1');
    expect(lastCall()[1]).toBeUndefined();
    expect(res.override?.mode).toBe('compact');
  });

  it('upserts the tier with a PUT carrying mode and warehouse_ids', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ effective: POLICY, override: POLICY }));
    await saveStockVisibility(
      { kind: 'access_type', accessTypeCode: 'dealer' },
      { mode: 'availability', warehouse_ids: ['wh-1', 'wh-2'], hide_zero_locations: false },
    );
    const [url, init] = lastCall();
    expect(url).toBe('/api/v1/inventory/stock-visibility/access-types/dealer');
    expect(init?.method).toBe('PUT');
    expect(JSON.parse(String(init?.body))).toEqual({
      mode: 'availability',
      warehouse_ids: ['wh-1', 'wh-2'],
      hide_zero_locations: false,
    });
  });

  it('round-trips hide_zero_locations: sent on the PUT, read back off the policy', async () => {
    // The backend defaults the key to false, so a body that omitted it would turn
    // the toggle off on every Save - and the card would look like it never stuck.
    apiFetch.mockResolvedValue(jsonResponse({ effective: POLICY, override: POLICY }));
    const res = await saveStockVisibility(
      { kind: 'contact', contactId: 'c-1' },
      { mode: 'compact', warehouse_ids: ['wh-1'], hide_zero_locations: true },
    );

    expect(JSON.parse(String(lastCall()[1]?.body))).toEqual({
      mode: 'compact',
      warehouse_ids: ['wh-1'],
      hide_zero_locations: true,
    });
    expect(res.override?.hide_zero_locations).toBe(true);
    expect(res.effective.hide_zero_locations).toBe(true);
  });

  it('sends warehouse_ids: null for "every active warehouse"', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ effective: POLICY, override: POLICY }));
    await saveStockVisibility(
      { kind: 'default' },
      { mode: 'detailed', warehouse_ids: null, hide_zero_locations: false },
    );
    expect(JSON.parse(String(lastCall()[1]?.body))).toEqual({
      mode: 'detailed',
      warehouse_ids: null,
      hide_zero_locations: false,
    });
  });

  it('hard-deletes an override', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ effective: POLICY, override: null }));
    await deleteStockVisibility({ kind: 'contact', contactId: 'c-1' });
    expect(lastCall()[0]).toBe('/api/v1/inventory/stock-visibility/contacts/c-1');
    expect(lastCall()[1]?.method).toBe('DELETE');
  });

  it('refuses to delete the default tier without asking the API - there is no such route', async () => {
    await expect(deleteStockVisibility({ kind: 'default' })).rejects.toThrow(
      'The default stock visibility policy cannot be removed',
    );
    expect(apiFetch).not.toHaveBeenCalled();
  });
});

describe('the warehouse pickers', () => {
  it('server-searches the existing warehouses route, active only', async () => {
    apiFetch.mockResolvedValue(
      jsonResponse({
        data: [
          { id: 'wh-1', warehouse_code: 'BRW', warehouse_name: 'Rawang Main Warehouse' },
          { id: 'wh-2', warehouse_code: 'BRW-BB', warehouse_name: null },
        ],
      }),
    );
    const rows = await searchStockVisibilityWarehouses('brw');

    const [url] = lastCall();
    expect(url.startsWith('/api/v1/inventory/warehouses?')).toBe(true);
    const q = queryOf(url);
    expect(q.get('query')).toBe('brw');
    expect(q.get('is_active')).toBe('true');
    expect(q.get('page')).toBe('1');
    expect(q.get('limit')).toBe('50');
    expect(q.get('segment')).toBeNull();
    expect(rows).toEqual([
      { id: 'wh-1', code: 'BRW', name: 'Rawang Main Warehouse' },
      { id: 'wh-2', code: 'BRW-BB', name: null },
    ]);
  });

  it('fills the Dealer pool from segment=dealer', async () => {
    apiFetch.mockResolvedValue(
      jsonResponse({
        data: [
          { id: 'wh-1', warehouse_code: 'BRW', warehouse_name: 'Rawang Main Warehouse' },
          { id: 'wh-3', warehouse_code: 'MWH', warehouse_name: 'Meru Warehouse' },
        ],
      }),
    );
    const rows = await getDealerPoolWarehouses();

    const q = queryOf(lastCall()[0]);
    expect(q.get('segment')).toBe('dealer');
    expect(q.get('is_active')).toBe('true');
    expect(q.get('query')).toBeNull();
    expect(rows.map((r) => r.code)).toEqual(['BRW', 'MWH']);
  });
});

describe('errors reach the caller as the API worded them', () => {
  it('throws the FastAPI detail on a rejected save', async () => {
    apiFetch.mockResolvedValue(
      jsonResponse({ detail: 'Unknown warehouse: wh-nope' }, { ok: false, status: 422 }),
    );
    await expect(
      saveStockVisibility(
        { kind: 'default' },
        { mode: 'detailed', warehouse_ids: ['wh-nope'], hide_zero_locations: false },
      ),
    ).rejects.toThrow('Unknown warehouse: wh-nope');
  });

  it('falls back to a readable message when the body carries none', async () => {
    apiFetch.mockResolvedValue(jsonResponse({}, { ok: false, status: 400 }));
    await expect(getStockVisibility({ kind: 'contact', contactId: 'c-1' })).rejects.toThrow(
      'Failed to load stock visibility',
    );
  });
});
