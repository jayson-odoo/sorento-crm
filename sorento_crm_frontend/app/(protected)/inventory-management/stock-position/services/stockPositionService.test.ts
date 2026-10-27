import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock('@/lib/api', () => api);
const blob = vi.hoisted(() => ({ saveBlobAs: vi.fn() }));
vi.mock('@/lib/save-blob', () => blob);

import { exportStockPosition, getStockPosition } from './stockPositionService';

const params = { pageIndex: 1, pageSize: 25, sorting: [{ id: 'wh:BRW', desc: true }], searchQuery: 'cwc' };

beforeEach(() => {
  api.apiFetch.mockReset();
  blob.saveBlobAs.mockReset();
});

describe('stockPositionService', () => {
  it('sends the DataGrid params and only the filters that are set', async () => {
    api.apiFetch.mockResolvedValue(new Response(JSON.stringify({ data: [] }), { status: 200 }));
    await getStockPosition(params, { supplierId: 's1', salesBasis: 'invoiced' });
    const url = new URL(api.apiFetch.mock.calls[0][0], 'http://x');
    expect(url.pathname).toBe('/api/v1/inventory/stock-position');
    expect(Object.fromEntries(url.searchParams)).toEqual({
      page: '2', limit: '25', sort: 'wh:BRW', dir: 'desc', query: 'cwc', supplier_id: 's1', sales_basis: 'invoiced',
    });
  });

  it('exports the same filtered, sorted set unpaged and saves the workbook', async () => {
    api.apiFetch.mockResolvedValue(new Response('xlsx', { status: 200 }));
    await exportStockPosition(params, { brandId: 'b1' });
    const url = new URL(api.apiFetch.mock.calls[0][0], 'http://x');
    expect(url.pathname).toBe('/api/v1/inventory/stock-position/export');
    expect(url.searchParams.get('page')).toBeNull();
    expect(url.searchParams.get('limit')).toBeNull();
    expect(url.searchParams.get('brand_id')).toBe('b1');
    expect(blob.saveBlobAs).toHaveBeenCalledWith(expect.anything(), 'stock-position.xlsx');
  });

  it('throws the server message on a failed read', async () => {
    api.apiFetch.mockResolvedValue(new Response(JSON.stringify({ detail: "Unknown sort column 'x'" }), { status: 422 }));
    await expect(getStockPosition(params, {})).rejects.toThrow("Unknown sort column 'x'");
  });
});
