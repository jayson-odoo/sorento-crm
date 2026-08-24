import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api';
import { getImportJobSourceUrl } from './importJobService';

const mockedFetch = vi.mocked(apiFetch);

function okResponse(body: unknown): Response {
  return { ok: true, json: async () => body } as Response;
}

beforeEach(() => vi.clearAllMocks());

describe('getImportJobSourceUrl - retained source-file download', () => {
  it('hits the /jobs/{id}/source endpoint and returns the signed url payload', async () => {
    mockedFetch.mockResolvedValue(
      okResponse({ url: 'https://signed.test/import-sources/abc/f.xlsx?sig=1', filename: 'f.xlsx', size: 123 }),
    );

    const res = await getImportJobSourceUrl('job-123');

    expect(mockedFetch).toHaveBeenCalledWith('/api/v1/system/jobs/job-123/source');
    expect(res.url).toContain('signed.test');
    expect(res.filename).toBe('f.xlsx');
    expect(res.size).toBe(123);
  });

  it('throws when the endpoint responds not-ok (e.g. 404 no source file)', async () => {
    mockedFetch.mockResolvedValue({ ok: false, json: async () => ({}) } as Response);

    await expect(getImportJobSourceUrl('job-404')).rejects.toThrow('Failed to fetch source file link');
  });
});
