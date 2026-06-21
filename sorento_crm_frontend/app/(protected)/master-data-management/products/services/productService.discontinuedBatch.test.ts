import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import { getProducts } from './productService';

const mockApiFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

function ok() {
  return {
    ok: true,
    status: 200,
    json: async () => ({ data: [], pagination: {} }),
  } as Response;
}

function calledUrl(): string {
  return String(mockApiFetch.mock.calls[0][0]);
}

beforeEach(() => {
  mockApiFetch.mockReset();
  mockApiFetch.mockResolvedValue(ok());
});

const base = { pageIndex: 0, pageSize: 50, sorting: [], searchQuery: '' };

describe('getProducts discontinued_batch_id param', () => {
  it('appends discontinued_batch_id when set', async () => {
    await getProducts({ ...base, discontinued_batch_id: 'batch-123' });
    expect(calledUrl()).toContain('discontinued_batch_id=batch-123');
  });

  it('omits discontinued_batch_id when not set', async () => {
    await getProducts({ ...base });
    expect(calledUrl()).not.toContain('discontinued_batch_id');
  });
});
