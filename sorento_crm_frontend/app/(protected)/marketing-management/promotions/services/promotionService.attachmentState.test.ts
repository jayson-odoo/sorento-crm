import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));
vi.mock('@/lib/helpers', () => ({ promotionFormDateToApiYyyyMmDd: (v: string) => v }));

import { apiFetch } from '@/lib/api';
import { getPromotions } from './promotionService';

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

describe('getPromotions attachment_state param', () => {
  it('appends attachment_state=unlinked', async () => {
    await getPromotions({ ...base, attachment_state: 'unlinked' });
    expect(calledUrl()).toContain('attachment_state=unlinked');
  });

  it('appends attachment_state=unlinked_or_trashed', async () => {
    await getPromotions({ ...base, attachment_state: 'unlinked_or_trashed' });
    expect(calledUrl()).toContain('attachment_state=unlinked_or_trashed');
  });

  it('omits attachment_state when not set', async () => {
    await getPromotions({ ...base });
    expect(calledUrl()).not.toContain('attachment_state');
  });
});
