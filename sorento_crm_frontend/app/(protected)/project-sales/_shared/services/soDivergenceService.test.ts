/**
 * P8a - the divergence service (contract section 6d).
 *
 * Two things are worth pinning at this layer. The BASE has to be the module's, because a
 * path that resolves to the wrong prefix 404s in a way that reads as "no reconciliation
 * exists". And an unmatched or ambiguous ingest is a 200 carrying a reason: it must resolve
 * rather than throw, or the caller cannot tell a person WHY the export did not land.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));
vi.mock('@/lib/api-client', () => ({
  extractApiError: vi.fn(async () => 'Backend said no'),
}));

import {
  downloadCorrectiveImportFile,
  getDivergence,
  ingestSalesOrderFile,
  listDivergences,
  resolveDivergenceRow,
} from './soDivergenceService';

function ok(body: unknown) {
  return { ok: true, json: async () => body, blob: async () => new Blob(['csv']) };
}

function fail() {
  return { ok: false, json: async () => ({}), blob: async () => new Blob() };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('listDivergences', () => {
  it('asks the project-sales module for its own path', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 1, limit: 25 } }));

    await listDivergences({ status: 'open' });

    const [url] = apiFetch.mock.calls[0];
    expect(url).toContain('/api/v1/project-sales/divergences');
    expect(url).toContain('status=open');
  });

  it('normalises a response whose envelope is missing', async () => {
    apiFetch.mockResolvedValue(ok({}));

    const result = await listDivergences();

    expect(result.data).toEqual([]);
    expect(result.total).toBe(0);
    expect(result.limit).toBe(25);
  });

  it('passes a project filter through', async () => {
    apiFetch.mockResolvedValue(ok({ data: [] }));

    await listDivergences({ project_id: 'p1', page: 2, limit: 10 });

    const [url] = apiFetch.mock.calls[0];
    expect(url).toContain('project_id=p1');
    expect(url).toContain('page=2');
    expect(url).toContain('limit=10');
  });

  it('surfaces the backend message on failure', async () => {
    apiFetch.mockResolvedValue(fail());

    await expect(listDivergences()).rejects.toThrow('Backend said no');
  });
});

describe('getDivergence', () => {
  it('addresses the reconciliation by id', async () => {
    apiFetch.mockResolvedValue(ok({ id: 'd1' }));

    await getDivergence('d1');

    expect(apiFetch.mock.calls[0][0]).toBe('/api/v1/project-sales/divergences/d1');
  });
});

describe('ingestSalesOrderFile', () => {
  it('posts the export as multipart form data', async () => {
    apiFetch.mockResolvedValue(ok({ outcome: 'divergent' }));
    const file = new File(['Item,Qty\nCB6633,600\n'], 'SO397450.csv', { type: 'text/csv' });

    await ingestSalesOrderFile(file);

    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toBe('/api/v1/project-sales/sales-orders/ingest-file');
    expect(init.method).toBe('POST');
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get('file')).toBe(file);
    // No Content-Type: the browser has to set the multipart boundary itself.
    expect(init.headers).toBeUndefined();
  });

  it('resolves rather than throws when nothing matched', async () => {
    apiFetch.mockResolvedValue(
      ok({ outcome: 'unmatched', message: 'No published sales order matches PO-778.' }),
    );

    const result = await ingestSalesOrderFile(
      new File(['x'], 'x.csv', { type: 'text/csv' }),
    );

    expect(result.outcome).toBe('unmatched');
    expect(result.message).toContain('PO-778');
  });
});

describe('resolveDivergenceRow', () => {
  it('sends the resolution and the reason as JSON', async () => {
    apiFetch.mockResolvedValue(ok({ id: 'd1', status: 'resolved' }));

    await resolveDivergenceRow('d1', 'r1', 'keep_ours', 'The PO says 600');

    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toBe('/api/v1/project-sales/divergences/d1/rows/r1/resolve');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({
      resolution: 'keep_ours',
      reason: 'The PO says 600',
    });
  });
});

describe('downloadCorrectiveImportFile', () => {
  it('returns the file as a blob', async () => {
    apiFetch.mockResolvedValue(ok(null));

    const blob = await downloadCorrectiveImportFile('d1');

    expect(apiFetch.mock.calls[0][0]).toBe(
      '/api/v1/project-sales/divergences/d1/corrective-import-file',
    );
    expect(blob).toBeInstanceOf(Blob);
  });

  it('throws when nothing was kept, so the caller can say why', async () => {
    apiFetch.mockResolvedValue(fail());

    await expect(downloadCorrectiveImportFile('d1')).rejects.toThrow('Backend said no');
  });
});
