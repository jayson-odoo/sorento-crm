import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api';
import { downloadImportJobSourceFile } from './importJobService';

const mockedFetch = vi.mocked(apiFetch);

beforeEach(() => vi.clearAllMocks());

describe('downloadImportJobSourceFile — retained source-file download', () => {
  it('hits the /jobs/{id}/source endpoint and returns the file blob', async () => {
    const blob = new Blob(['excel-bytes'], { type: 'application/octet-stream' });
    mockedFetch.mockResolvedValue({ ok: true, blob: async () => blob } as unknown as Response);

    const res = await downloadImportJobSourceFile('job-123');

    expect(mockedFetch).toHaveBeenCalledWith('/api/v1/system/jobs/job-123/source');
    expect(res).toBe(blob);
  });

  it('throws when the endpoint responds not-ok (e.g. 404 no source file)', async () => {
    mockedFetch.mockResolvedValue({ ok: false } as Response);

    await expect(downloadImportJobSourceFile('job-404')).rejects.toThrow('Failed to download source file');
  });
});
