/**
 * AC-ST307 / AC-ST309 (FE half): the portal's conversation read. `portalFetch` is the seam,
 * `unwrap` / `extractApiError` stay real.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./portal-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./portal-client')>();
  return { ...actual, portalFetch: vi.fn() };
});

import { portalFetch } from './portal-client';
import { NotASalesAgentError, getAskConversation } from './customer-asks-service';

const mockFetch = vi.mocked(portalFetch);
const BASE = '/api/v1/public/portal/customer-asks';
const CONVERSATION = {
  messages: [{ id: 5, direction: 'out', text: 'SRT5674 x 50: yes', at: '2026-09-29T03:00:00' }],
  ask_message_id: 5,
};

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as never;
}
function fail(status: number, message: string) {
  return {
    ok: false,
    status,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => ({ message }),
    text: async () => JSON.stringify({ message }),
  } as never;
}

beforeEach(() => mockFetch.mockReset());

describe('getAskConversation (portal)', () => {
  it('GETs the conversation of one ask', async () => {
    mockFetch.mockResolvedValue(ok(CONVERSATION));
    await expect(getAskConversation('ask-1', { wholeDay: false })).resolves.toEqual(CONVERSATION);
    const url = String(mockFetch.mock.calls[0][0]);
    expect(url.startsWith(`${BASE}/ask-1/conversation`)).toBe(true);
    expect(url).not.toContain('whole_day=true');
  });

  it('adds whole_day=true for the whole day', async () => {
    mockFetch.mockResolvedValue(ok(CONVERSATION));
    await getAskConversation('ask-1', { wholeDay: true });
    expect(String(mockFetch.mock.calls[0][0])).toBe(`${BASE}/ask-1/conversation?whole_day=true`);
  });

  it('throws the server message, and NotASalesAgentError on a 403', async () => {
    mockFetch.mockResolvedValue(fail(404, 'Stock ask not found'));
    await expect(getAskConversation('ask-9', { wholeDay: false })).rejects.toThrow('Stock ask not found');
    mockFetch.mockResolvedValue(fail(403, 'nope'));
    await expect(getAskConversation('ask-9', { wholeDay: false })).rejects.toBeInstanceOf(NotASalesAgentError);
  });
});
