/**
 * AFTER-SALES-P2 red tests (UAC J, F1, F2): the wire contract of the job product lines and the
 * warranty list filter. A key typo is a silently dropped field on the backend, so paths, methods
 * and bodies are asserted.
 *
 * Module extended: `./serviceJobService` gains
 *   getServiceJobProducts(jobId)                       GET    /api/v1/after-sales/service-jobs/{id}/products
 *   addServiceJobProduct(jobId, values)                POST   .../products   body { product_id, kind_id, purchase_date, defect_type_id }
 *   updateServiceJobProduct(jobId, lineId, values)     PATCH  .../products/{lineId}
 *   deleteServiceJobProduct(jobId, lineId)             DELETE .../products/{lineId}
 *   searchCatalogueProducts(query)                     -> { id, product_code, product_name }[]
 * and `ServiceJobsListParams` gains `warranty_summary?: string[]` (repeated query param).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', () => ({ apiFetch }));

import {
  addServiceJobProduct,
  deleteServiceJobProduct,
  getServiceJobProducts,
  getServiceJobs,
  updateServiceJobProduct,
} from './serviceJobService';

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as Response;
const BASE = '/api/v1/after-sales/service-jobs/j-1/products';

beforeEach(() => apiFetch.mockReset());

describe('serviceJobService product lines', () => {
  it('lists the lines of a job', async () => {
    apiFetch.mockResolvedValue(ok([]));
    await getServiceJobProducts('j-1');
    expect(apiFetch).toHaveBeenLastCalledWith(BASE);
  });

  it('adds a line with the four backend keys', async () => {
    apiFetch.mockResolvedValue(ok({ id: 'l-1' }));
    await addServiceJobProduct('j-1', {
      product_id: 'p-1', kind_id: 'k-1', purchase_date: '2020-03-15', defect_type_id: 'd-1',
    });
    const [url, init] = apiFetch.mock.calls.at(-1)!;
    expect(url).toBe(BASE);
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({
      product_id: 'p-1', kind_id: 'k-1', purchase_date: '2020-03-15', defect_type_id: 'd-1',
    });
  });

  it('edits a line with PATCH', async () => {
    apiFetch.mockResolvedValue(ok({ id: 'l-1' }));
    await updateServiceJobProduct('j-1', 'l-1', { kind_id: null, purchase_date: null, defect_type_id: null });
    const [url, init] = apiFetch.mock.calls.at(-1)!;
    expect(url).toBe(`${BASE}/l-1`);
    expect(init.method).toBe('PATCH');
    expect(JSON.parse(init.body)).toEqual({ kind_id: null, purchase_date: null, defect_type_id: null });
  });

  it('removes a line with DELETE', async () => {
    apiFetch.mockResolvedValue(ok({ message: 'ok' }));
    await deleteServiceJobProduct('j-1', 'l-1');
    const [url, init] = apiFetch.mock.calls.at(-1)!;
    expect(url).toBe(`${BASE}/l-1`);
    expect(init.method).toBe('DELETE');
  });

  it('a failed add throws the server message', async () => {
    apiFetch.mockResolvedValue({
      ok: false, status: 422, headers: new Headers({ 'content-type': 'application/json' }), json: async () => ({ detail: 'Purchase date cannot be in the future' }),
    } as Response);
    await expect(
      addServiceJobProduct('j-1', { product_id: 'p-1', kind_id: null, purchase_date: null, defect_type_id: null }),
    ).rejects.toThrow(/Purchase date cannot be in the future/);
  });
});

describe('serviceJobService list: Warranty filter', () => {
  it('sends warranty_summary as a repeated param', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 1, limit: 50 } }));
    await getServiceJobs({
      pageIndex: 0, pageSize: 50, sorting: [{ id: 'warranty_summary', desc: false }], searchQuery: '',
      warranty_summary: ['covered', 'unknown'],
    } as never);
    const url = String(apiFetch.mock.calls.at(-1)![0]);
    expect(url).toContain('warranty_summary=covered&warranty_summary=unknown');
    expect(url).toContain('sort=warranty_summary');
  });
});
