/**
 * S2b Phase 2 test-first (AC-255, list half). Genuinely RED: unlike the drawer-level
 * "Failed turns only" filter (`ChatTranscript.failedOnly.test.tsx`, Phase 1, already
 * green), the Chat History LIST's own "Failed turns only" filter - AC-255's "only
 * contacts with a failed turn in the range are listed, and the row shows the last
 * failed stage" - has no code anywhere yet: no service function, no hook, no toggle in
 * `page.tsx`. `page.tsx` already has the exact shape this needs (`breachedOnly`, a
 * boolean `useState` that widens the query filter, right next to where this belongs).
 *
 * ASSUMPTION (flagged to the captain/coder, matching the module docstring in
 * `test_turns_admin_api.py` on the backend): the service exposes
 * `getFailedChatbotContacts(filters)` calling
 * `GET /api/v1/system/chatbot/turns/failed-contacts?from=&to=`, returning
 * `{ items: [{ contact_respond_id, last_failed_stage, last_failed_at, count }] }`. This
 * is NOT documented in the `chatbotTurnService.ts` contract comment today - only
 * `getChatbotTurns` and `retryChatbotTurn` are. The coder should update that doc-comment
 * alongside adding the function, so the contract stays the single place both ends read.
 *
 * This test is expected to fail with "getFailedChatbotContacts is not a function" (the
 * export does not exist), not a fixture bug - confirmed by the red run quoted in the
 * tester's report.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

beforeEach(() => {
  apiFetch.mockReset();
});

describe('getFailedChatbotContacts (AC-255)', () => {
  it('calls GET /api/v1/system/chatbot/turns/failed-contacts with the from/to range', async () => {
    apiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [
          {
            contact_respond_id: 'ZZT-contact-1',
            last_failed_stage: 'access',
            last_failed_at: '2026-09-05T05:00:00.000Z',
            count: 2,
          },
        ],
      }),
    });

    const { getFailedChatbotContacts } = await import('./chatbotTurnService');
    const result = await getFailedChatbotContacts({
      from: '2026-09-04T00:00:00.000Z',
      to: '2026-09-05T00:00:00.000Z',
    });

    expect(apiFetch).toHaveBeenCalledTimes(1);
    const [url] = apiFetch.mock.calls[0];
    expect(url).toContain('/api/v1/system/chatbot/turns/failed-contacts');
    expect(url).toContain('from=');
    expect(url).toContain('to=');

    expect(result.items).toHaveLength(1);
    expect(result.items[0]).toMatchObject({
      contact_respond_id: 'ZZT-contact-1',
      last_failed_stage: 'access',
      count: 2,
    });
  });

  it('throws the extracted error message on a non-ok response', async () => {
    apiFetch.mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'boom' }),
    });

    const { getFailedChatbotContacts } = await import('./chatbotTurnService');
    await expect(getFailedChatbotContacts({})).rejects.toThrow();
  });
});
