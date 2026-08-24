/**
 * C4 - lookup binding 403 must degrade gracefully (no throw → no react-query
 * retry, no global "Permission required" toast). Other failures still throw.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { getLookupOptionsByBinding } from './lookupBindingService';
import { apiFetch } from '@/lib/api';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

const mockFetch = vi.mocked(apiFetch);

function res(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

describe('getLookupOptionsByBinding', () => {
  beforeEach(() => mockFetch.mockReset());

  it('returns options on success', async () => {
    mockFetch.mockResolvedValueOnce(
      res(200, { set_key: 'complaint_type', set_name: 'Complaint Type', options: [{ value: 'leak', label: 'Leak', keywords: [], is_active: true }] }),
    );
    const r = await getLookupOptionsByBinding('complaints', 'complaint_type');
    expect(r.set_key).toBe('complaint_type');
    expect(r.options).toHaveLength(1);
    expect(r.forbidden).toBeUndefined();
  });

  it('degrades on 403 - resolves forbidden with empty options, does NOT throw', async () => {
    mockFetch.mockResolvedValueOnce(res(403, { detail: 'Permission required: master_data.lookup_sets.view' }));
    const r = await getLookupOptionsByBinding('complaints', 'complaint_type');
    expect(r.forbidden).toBe(true);
    expect(r.set_key).toBeNull();
    expect(r.options).toEqual([]);
  });

  it('still throws on a real failure (500)', async () => {
    mockFetch.mockResolvedValueOnce(res(500, { detail: 'boom' }));
    await expect(getLookupOptionsByBinding('complaints', 'complaint_type')).rejects.toThrow();
  });
});
