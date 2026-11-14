/**
 * FORMS-LAST-ACTIVITY browser-pass fix: with no sort chosen (header cycled to off) the Purchase requests list
 * asks for its default, last activity newest first, never oldest first.
 */
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    apiFetch: vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ data: [], pagination: {} }) }) as unknown as Response),
  };
});

import { apiFetch } from '@/lib/api';
import { getPurchaseRequests } from './purchaseRequestService';

const sentQuery = () => {
  const calls = (apiFetch as unknown as ReturnType<typeof vi.fn>).mock.calls;
  return new URLSearchParams(String(calls[calls.length - 1][0]).split('?')[1]);
};

describe('getPurchaseRequests - empty sorting', () => {
  it('sends last_activity_at descending', async () => {
    await getPurchaseRequests({ pageIndex: 0, pageSize: 50, sorting: [], searchQuery: '' });
    expect(sentQuery().get('sort')).toBe('last_activity_at');
    expect(sentQuery().get('dir')).toBe('desc');
  });

  it('keeps an explicit ascending sort', async () => {
    await getPurchaseRequests({ pageIndex: 0, pageSize: 50, sorting: [{ id: 'last_activity_at', desc: false }], searchQuery: '' });
    expect(sentQuery().get('dir')).toBe('asc');
  });
});
