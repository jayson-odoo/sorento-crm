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
    await getStockPosition(params, { supplierIds: ['s1'] });
    const url = new URL(api.apiFetch.mock.calls[0][0], 'http://x');
    expect(url.pathname).toBe('/api/v1/inventory/stock-position');
    expect(Object.fromEntries(url.searchParams)).toEqual({
      page: '2', limit: '25', sort: 'wh:BRW', dir: 'desc', query: 'cwc', supplier_id: 's1',
    });
  });

  it('exports the same filtered, sorted set unpaged and saves the workbook', async () => {
    api.apiFetch.mockResolvedValue(new Response('xlsx', { status: 200 }));
    await exportStockPosition(params, { brandIds: ['b1'] });
    const url = new URL(api.apiFetch.mock.calls[0][0], 'http://x');
    expect(url.pathname).toBe('/api/v1/inventory/stock-position/export');
    expect(url.searchParams.get('page')).toBeNull();
    expect(url.searchParams.get('limit')).toBeNull();
    expect(url.searchParams.get('brand_id')).toBe('b1');
    expect(blob.saveBlobAs).toHaveBeenCalledWith(expect.anything(), 'stock-position.xlsx');
  });

  it('sends several values of a filter comma-joined in one param, and the export the same (FILTER-MULTISELECT)', async () => {
    api.apiFetch.mockResolvedValue(new Response(JSON.stringify({ data: [] }), { status: 200 }));
    const filters = { supplierIds: ['s1', 's2'], brandIds: ['b1', 'b2', 'b3'], warehouseIds: ['w1', 'w2'] };
    await getStockPosition(params, filters);
    const read = new URL(api.apiFetch.mock.calls[0][0], 'http://x').searchParams;
    expect(read.getAll('supplier_id')).toEqual(['s1,s2']);
    expect(read.getAll('brand_id')).toEqual(['b1,b2,b3']);
    expect(read.getAll('warehouse_id')).toEqual(['w1,w2']);
    api.apiFetch.mockResolvedValue(new Response('xlsx', { status: 200 }));
    await exportStockPosition(params, filters);
    const exp = new URL(api.apiFetch.mock.calls[1][0], 'http://x').searchParams;
    expect(exp.get('supplier_id')).toBe('s1,s2');
    expect(exp.get('brand_id')).toBe('b1,b2,b3');
    expect(exp.get('warehouse_id')).toBe('w1,w2');
    expect(exp.get('sort')).toBe('wh:BRW');
  });

  it('leaves an empty selection out of the query (no filter)', async () => {
    api.apiFetch.mockResolvedValue(new Response(JSON.stringify({ data: [] }), { status: 200 }));
    await getStockPosition(params, { supplierIds: [], brandIds: [], warehouseIds: [] });
    const read = new URL(api.apiFetch.mock.calls[0][0], 'http://x').searchParams;
    expect(read.has('supplier_id') || read.has('brand_id') || read.has('warehouse_id')).toBe(false);
  });

  it('exports only the warehouse columns the user shows; none shown is an empty code, not all', async () => {
    api.apiFetch.mockResolvedValue(new Response('xlsx', { status: 200 }));
    await exportStockPosition(params, {}, ['BRW', 'DC1']);
    expect(new URL(api.apiFetch.mock.calls[0][0], 'http://x').searchParams.getAll('wh')).toEqual(['BRW', 'DC1']);
    api.apiFetch.mockResolvedValue(new Response('xlsx', { status: 200 }));
    await exportStockPosition(params, {}, []);
    expect(new URL(api.apiFetch.mock.calls[1][0], 'http://x').searchParams.getAll('wh')).toEqual(['']);
  });

  it('throws the server message on a failed read', async () => {
    api.apiFetch.mockResolvedValue(new Response(JSON.stringify({ detail: "Unknown sort column 'x'" }), { status: 422 }));
    await expect(getStockPosition(params, {})).rejects.toThrow("Unknown sort column 'x'");
  });
});
