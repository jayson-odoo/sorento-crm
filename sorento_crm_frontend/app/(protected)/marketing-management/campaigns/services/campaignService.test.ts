import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api';
import { getCampaignTypes } from './campaignService';

const mockedFetch = vi.mocked(apiFetch);

beforeEach(() => vi.clearAllMocks());

describe('getCampaignTypes (Bug A1 crash fix)', () => {
  it('unwraps a paginated `{data:[...]}` envelope into an array', async () => {
    mockedFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        data: [{ id: 't1', type_name: 'Seasonal' }],
        pagination: { total: 1 },
      }),
    } as Response);

    const out = await getCampaignTypes();
    expect(Array.isArray(out)).toBe(true);
    expect(out).toHaveLength(1);
    expect(out[0].type_name).toBe('Seasonal');
  });

  it('passes through a bare array response', async () => {
    mockedFetch.mockResolvedValue({
      ok: true,
      json: async () => [{ id: 't1', type_name: 'Launch' }],
    } as Response);

    const out = await getCampaignTypes();
    expect(out).toHaveLength(1);
  });

  it('returns [] when envelope has no data', async () => {
    mockedFetch.mockResolvedValue({
      ok: true,
      json: async () => ({}),
    } as Response);

    expect(await getCampaignTypes()).toEqual([]);
  });
});
