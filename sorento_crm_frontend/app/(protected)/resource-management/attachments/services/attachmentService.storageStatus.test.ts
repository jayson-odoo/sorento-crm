import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import { getAttachments } from './attachmentService';

const mockApiFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

function ok() {
  return { ok: true, status: 200, json: async () => ({ data: [], pagination: {} }) } as Response;
}

function calledUrl(): string {
  return String(mockApiFetch.mock.calls[0][0]);
}

beforeEach(() => {
  mockApiFetch.mockReset();
  mockApiFetch.mockResolvedValue(ok());
});

const base = { pageIndex: 0, pageSize: 50, sorting: [], searchQuery: '' };

describe('getAttachments storage_status param', () => {
  it('appends storage_status=missing when set', async () => {
    await getAttachments({ ...base, storage_status: 'missing' });
    expect(calledUrl()).toContain('storage_status=missing');
  });

  it('appends storage_status=accessible when set', async () => {
    await getAttachments({ ...base, storage_status: 'accessible' });
    expect(calledUrl()).toContain('storage_status=accessible');
  });

  it('omits storage_status when not set', async () => {
    await getAttachments({ ...base });
    expect(calledUrl()).not.toContain('storage_status');
  });
});
