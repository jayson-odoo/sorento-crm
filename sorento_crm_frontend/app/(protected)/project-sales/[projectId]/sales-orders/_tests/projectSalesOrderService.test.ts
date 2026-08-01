/**
 * The service seam: the list envelope, the DataGrid params, and how a refused publish reads.
 *
 * Pinned because integration corrected the contract on 2026-08-02: list responses are the
 * repo's `{data, pagination: {...}}` and NOT the flat `{data, total, page, limit}` the
 * contract first described. Both are accepted, and that has to stay true.
 *
 * Lives under `sales-orders/_tests/` rather than beside the service because this slice owns
 * the `sales-orders/**` tree while seven other workstreams are in the same repo. An
 * underscore-prefixed folder is never routed by Next.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

import {
  listProjectSalesOrders,
  publishSalesOrder,
} from '../../../_shared/services/projectSalesOrderService';

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

beforeEach(() => {
  apiFetch.mockReset();
});

describe('listProjectSalesOrders', () => {
  it('reads the total off the standard pagination envelope', async () => {
    apiFetch.mockResolvedValue(
      jsonResponse({
        data: [{ id: 'so-1' }],
        pagination: { total: 37, page: 2, limit: 25 },
        empty: false,
      }),
    );

    const envelope = await listProjectSalesOrders('p1', { page: 2, limit: 25 });

    expect(envelope.total).toBe(37);
    expect(envelope.page).toBe(2);
    expect(envelope.limit).toBe(25);
    expect(envelope.data).toHaveLength(1);
  });

  it('still reads a flat envelope, so an early backend does not blank the grid', async () => {
    apiFetch.mockResolvedValue(
      jsonResponse({ data: [{ id: 'so-1' }], total: 3, page: 1, limit: 25 }),
    );

    const envelope = await listProjectSalesOrders('p1');

    expect(envelope.total).toBe(3);
  });

  it('falls back to the row count when neither shape carries a total', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ data: [{ id: 'a' }, { id: 'b' }] }));

    const envelope = await listProjectSalesOrders('p1');

    expect(envelope.total).toBe(2);
  });

  it('sends the shared DataGrid params rather than a hand-built query', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ data: [], pagination: { total: 0 } }));

    await listProjectSalesOrders('p1', {
      page: 3,
      limit: 50,
      sort: 'created_at',
      dir: 'desc',
      query: 'TOWER',
      status: 'blocked',
    });

    const url = String(apiFetch.mock.calls[0][0]);
    expect(url).toContain('/api/v1/project-sales/projects/p1/sales-orders?');
    expect(url).toContain('page=3');
    expect(url).toContain('limit=50');
    expect(url).toContain('sort=created_at');
    expect(url).toContain('dir=desc');
    expect(url).toContain('query=TOWER');
    expect(url).toContain('status=blocked');
  });

  it('surfaces the server sentence when the list fails', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ detail: 'Module projects is disabled' }, 403));

    await expect(listProjectSalesOrders('p1')).rejects.toThrow('Module projects is disabled');
  });
});

describe('publishSalesOrder', () => {
  it('passes the 409 sentence through, blocking findings and all', async () => {
    apiFetch.mockResolvedValue(
      jsonResponse(
        { detail: 'Line 1: 600 x 11.16 is 6,696.00 but the PO says 6,690.00.' },
        409,
      ),
    );

    await expect(publishSalesOrder('so-1')).rejects.toThrow(
      'Line 1: 600 x 11.16 is 6,696.00 but the PO says 6,690.00.',
    );
  });

  it('returns the reference and the import file on success', async () => {
    apiFetch.mockResolvedValue(
      jsonResponse({
        status: 'published',
        provisional_ref: 'PSO-000123',
        import_file_url: 'https://example.test/import.csv',
      }),
    );

    const result = await publishSalesOrder('so-1');

    expect(result.provisional_ref).toBe('PSO-000123');
    expect(result.import_file_url).toBe('https://example.test/import.csv');
  });
});
