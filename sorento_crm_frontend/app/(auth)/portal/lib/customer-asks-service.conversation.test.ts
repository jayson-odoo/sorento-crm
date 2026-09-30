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
import { NotASalesAgentError, getAskConversation, getAskConversationPage, searchAskConversation } from './customer-asks-service';

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
    await expect(getAskConversation('ask-1')).resolves.toEqual(CONVERSATION);
    const url = String(mockFetch.mock.calls[0][0]);
    expect(url).toBe(`${BASE}/ask-1/conversation`);
  });

  it('throws the server message, and NotASalesAgentError on a 403', async () => {
    mockFetch.mockResolvedValue(fail(404, 'Stock ask not found'));
    await expect(getAskConversation('ask-9')).rejects.toThrow('Stock ask not found');
    mockFetch.mockResolvedValue(fail(403, 'nope'));
    await expect(getAskConversation('ask-9')).rejects.toBeInstanceOf(NotASalesAgentError);
  });
});

// ASKS-UX item 3 (AC-AU12): the shared thread's two loaders, portal-keyed.
describe('getAskConversationPage / searchAskConversation (portal)', () => {
  const PAGE = { items: [], has_more_older: false, has_more_newer: false, oldest_message_id: null, newest_message_id: null };

  it('GETs the tail with no cursor, and one cursor when given', async () => {
    mockFetch.mockResolvedValue(ok(PAGE));
    await expect(getAskConversationPage('ask-1', { limit: 50 })).resolves.toEqual(PAGE);
    expect(String(mockFetch.mock.calls[0][0])).toBe(`${BASE}/ask-1/conversation/page?limit=50`);
    await getAskConversationPage('ask-1', { around: '123', limit: 50 });
    expect(String(mockFetch.mock.calls[1][0])).toBe(`${BASE}/ask-1/conversation/page?around=123&limit=50`);
    await getAskConversationPage('ask-1', { before: '99' });
    expect(String(mockFetch.mock.calls[2][0])).toBe(`${BASE}/ask-1/conversation/page?before=99`);
  });

  it('search returns the items of the search body', async () => {
    const hit = { message_id: '5', sent_at: '2026-09-29T03:00:00', direction: 'outgoing', snippet: 'yes' };
    mockFetch.mockResolvedValue(ok({ items: [hit], total: 1, truncated: false, query: 'yes' }));
    await expect(searchAskConversation('ask-1', 'yes')).resolves.toEqual([hit]);
    expect(String(mockFetch.mock.calls[0][0])).toBe(`${BASE}/ask-1/conversation/search?q=yes&limit=100`);
  });

  it('throws the server message, and NotASalesAgentError on a 403', async () => {
    mockFetch.mockResolvedValue(fail(404, 'Stock ask not found'));
    await expect(getAskConversationPage('ask-9', {})).rejects.toThrow('Stock ask not found');
    await expect(searchAskConversation('ask-9', 'x')).rejects.toThrow('Stock ask not found');
    mockFetch.mockResolvedValue(fail(403, 'nope'));
    await expect(getAskConversationPage('ask-9', {})).rejects.toBeInstanceOf(NotASalesAgentError);
  });
});
