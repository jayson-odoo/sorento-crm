/**
 * PLAN-excel-preview-26sep S1 (AC-1, AC-6): the low stock report page's service. The view
 * read sends the split and repeats `supplier` / `category` once per chosen value; the export
 * posts the same split and filters so the file is the view.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { exportLowStockReport, getLowStockView } from './lowStockReportService';

function ok(body: unknown) {
  return {
    ok: true,
    headers: { get: () => 'application/json' },
    json: async () => body,
  } as unknown as Response;
}

function refused(status: number, detail: string) {
  return {
    ok: false,
    status,
    headers: { get: () => 'application/json' },
    json: async () => ({ detail }),
    clone() {
      return this;
    },
  } as unknown as Response;
}

beforeEach(() => apiFetch.mockReset());

describe('getLowStockView', () => {
  it('GETs the view with the split and one repeated param per filter value', async () => {
    apiFetch.mockResolvedValue(ok({ counts: { rows: 1 } }));
    await getLowStockView({
      runId: 'run-1',
      split: 'supplier',
      suppliers: ['Acme', 'No supplier'],
      categories: ['BASIN'],
    });
    const url = new URL(String(apiFetch.mock.calls[0][0]), 'http://x');
    expect(url.pathname).toBe('/api/v1/scm/order-summary/low-stock-view');
    expect(url.searchParams.get('run_id')).toBe('run-1');
    expect(url.searchParams.get('split')).toBe('supplier');
    expect(url.searchParams.getAll('supplier')).toEqual(['Acme', 'No supplier']);
    expect(url.searchParams.getAll('category')).toEqual(['BASIN']);
  });

  it('omits run_id for the newest run, and empty filters', async () => {
    apiFetch.mockResolvedValue(ok({}));
    await getLowStockView({ split: 'supplier_category', suppliers: [], categories: [] });
    const url = new URL(String(apiFetch.mock.calls[0][0]), 'http://x');
    expect(url.searchParams.has('run_id')).toBe(false);
    expect(url.searchParams.has('supplier')).toBe(false);
    expect(url.searchParams.has('category')).toBe(false);
  });

  it('throws the extracted message on a refusal', async () => {
    apiFetch.mockResolvedValue(refused(404, 'Reorder run not found'));
    await expect(
      getLowStockView({ runId: 'x', split: 'none', suppliers: [], categories: [] }),
    ).rejects.toThrow('Reorder run not found');
  });
});

describe('exportLowStockReport', () => {
  it('POSTs the low stock format with the same split and filters', async () => {
    apiFetch.mockResolvedValue(ok({ id: 'dl-1', status: 'pending' }));
    const row = await exportLowStockReport({
      runId: 'run-1',
      split: 'category',
      suppliers: ['Acme'],
      categories: [],
    });
    expect(row).toEqual({ id: 'dl-1', status: 'pending' });
    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toBe('/api/v1/scm/order-summary/export');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({
      run_id: 'run-1',
      format: 'low_stock_xlsx',
      split: 'category',
      suppliers: ['Acme'],
      categories: [],
    });
  });

  it('throws the extracted message on a 409', async () => {
    apiFetch.mockResolvedValue(refused(409, 'A low stock report for this plan is already being prepared'));
    await expect(
      exportLowStockReport({ runId: 'r', split: 'none', suppliers: [], categories: [] }),
    ).rejects.toThrow('already being prepared');
  });
});
