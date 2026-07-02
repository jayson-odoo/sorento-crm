import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(),
}));
vi.mock('@/lib/api-client', () => ({
  extractApiError: vi.fn(),
}));

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import { bulkUpdateSuppliers } from './supplierBulkUpdateService';

const mockedFetch = vi.mocked(apiFetch);
const mockedExtract = vi.mocked(extractApiError);

beforeEach(() => vi.clearAllMocks());

describe('bulkUpdateSuppliers', () => {
  it('POSTs { ids, field, value } to the bulk-update endpoint and returns the result', async () => {
    mockedFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ updated: 2, skipped: [] }),
    } as Response);

    const out = await bulkUpdateSuppliers(['s1', 's2'], 'is_active', 'false');

    expect(mockedFetch).toHaveBeenCalledTimes(1);
    const [url, init] = mockedFetch.mock.calls[0];
    expect(url).toBe('/api/v1/procurement/suppliers/bulk-update');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init?.body as string)).toEqual({
      ids: ['s1', 's2'],
      field: 'is_active',
      value: 'false',
    });
    expect(out).toEqual({ updated: 2, skipped: [] });
  });

  it('returns the partial-success shape (updated + skipped rows)', async () => {
    mockedFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        updated: 1,
        skipped: [{ id: 's2', label: 'Beta Supplies', reason: 'Record not found.' }],
      }),
    } as Response);

    const out = await bulkUpdateSuppliers(['s1', 's2'], 'is_active', 'true');
    expect(out.updated).toBe(1);
    expect(out.skipped).toHaveLength(1);
    expect(out.skipped[0].reason).toBe('Record not found.');
  });

  it('throws the extractApiError message on a non-ok response (no hand-rolled parse)', async () => {
    const response = { ok: false } as Response;
    mockedFetch.mockResolvedValue(response);
    mockedExtract.mockResolvedValue('Field is not editable in bulk.');

    await expect(bulkUpdateSuppliers(['s1'], 'supplier_name', 'x')).rejects.toThrow(
      'Field is not editable in bulk.',
    );
    expect(mockedExtract).toHaveBeenCalledWith(response, 'Failed to bulk-update suppliers');
  });
});
