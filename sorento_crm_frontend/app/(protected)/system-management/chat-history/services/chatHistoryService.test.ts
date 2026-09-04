/**
 * S2b hardening (FE 1a): `buildParams` (private to `chatHistoryService.ts`) appends a
 * repeated `contact_id` rather than comma-joining it, which is what the backend's
 * `_apply_filters` expects (`app/services/chat_history_query.py`, and
 * `tests/chatbot/test_turns_admin_api.py`'s several-ids case on the other side of the
 * wire). Not exported, so tested through `getChatMessages`'s actual request URL - the
 * public seam, and the one that would break silently for a real user if this regressed.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockResolvedValue({
    ok: true,
    json: async () => ({ data: [], pagination: { total: 0, page: 1 } }),
  });
});

describe('getChatMessages contact_id (S2b hardening 1a)', () => {
  it('appends each contact_id as its own repeated query param, not comma-joined', async () => {
    const { getChatMessages } = await import('./chatHistoryService');
    await getChatMessages({ contact_id: ['ZZT-a', 'ZZT-b', 'ZZT-c'] });

    const [url] = apiFetch.mock.calls[0];
    const params = new URLSearchParams(String(url).split('?')[1]);
    expect(params.getAll('contact_id')).toEqual(['ZZT-a', 'ZZT-b', 'ZZT-c']);
    // Not a single joined value - that would be read as one contact id nobody has.
    expect(url).not.toContain('ZZT-a%2CZZT-b');
    expect(url).not.toContain('ZZT-a,ZZT-b');
  });

  it('sends a single contact_id as one plain value, not a repeated param', async () => {
    const { getChatMessages } = await import('./chatHistoryService');
    await getChatMessages({ contact_id: 'ZZT-solo' });

    const [url] = apiFetch.mock.calls[0];
    const params = new URLSearchParams(String(url).split('?')[1]);
    expect(params.getAll('contact_id')).toEqual(['ZZT-solo']);
  });

  it('sends no contact_id param at all when the filter is absent', async () => {
    const { getChatMessages } = await import('./chatHistoryService');
    await getChatMessages({});

    const [url] = apiFetch.mock.calls[0];
    const params = new URLSearchParams(String(url).split('?')[1]);
    expect(params.has('contact_id')).toBe(false);
  });
});
