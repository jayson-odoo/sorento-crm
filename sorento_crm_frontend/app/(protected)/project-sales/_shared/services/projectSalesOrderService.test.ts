/**
 * The AutoCount import file, at the service layer.
 *
 * The defect this pins: `import_file_url` is a path on the BACKEND, so handing it to an
 * `<a href download>` resolves it against the frontend origin and 404s. The file is fetched
 * through the api client instead, which addresses the module's own path and carries the
 * bearer token, and the name comes off the response the backend stamped.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));
vi.mock('@/lib/api-client', () => ({
  extractApiError: vi.fn(async () => 'Backend said no'),
  buildDataGridParams: vi.fn(() => new URLSearchParams()),
}));

import { downloadSalesOrderImportFile } from './projectSalesOrderService';

function ok(disposition: string | null) {
  return {
    ok: true,
    blob: async () => new Blob(['Item,Qty\nCB6633,600\n'], { type: 'text/csv' }),
    headers: { get: (name: string) => (name === 'Content-Disposition' ? disposition : null) },
  };
}

function fail() {
  return {
    ok: false,
    json: async () => ({}),
    blob: async () => new Blob(),
    headers: { get: () => null },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('downloadSalesOrderImportFile', () => {
  it('asks the backend route, not a frontend path', async () => {
    apiFetch.mockResolvedValue(ok('attachment; filename="SO376200.csv"'));

    await downloadSalesOrderImportFile('so-1');

    expect(apiFetch.mock.calls[0][0]).toBe(
      '/api/v1/project-sales/sales-orders/so-1/import-file',
    );
  });

  it('returns the bytes and the name the backend stamped on them', async () => {
    apiFetch.mockResolvedValue(ok('attachment; filename="SO376200.csv"'));

    const file = await downloadSalesOrderImportFile('so-1');

    expect(file.blob).toBeInstanceOf(Blob);
    expect(file.filename).toBe('SO376200.csv');
  });

  it('reports no name when the response carries no disposition, so the caller can fall back', async () => {
    apiFetch.mockResolvedValue(ok(null));

    const file = await downloadSalesOrderImportFile('so-1');

    expect(file.filename).toBeNull();
  });

  it('reads an unquoted filename too', async () => {
    apiFetch.mockResolvedValue(ok('attachment; filename=SO376200.csv'));

    const file = await downloadSalesOrderImportFile('so-1');

    expect(file.filename).toBe('SO376200.csv');
  });

  it('surfaces the backend message rather than saving an error page as a csv', async () => {
    apiFetch.mockResolvedValue(fail());

    await expect(downloadSalesOrderImportFile('so-1')).rejects.toThrow('Backend said no');
  });
});
