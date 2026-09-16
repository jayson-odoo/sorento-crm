/**
 * AC-1516 (chatbot-turn-rearch, S1): the service documents its API contract at the
 * top (see the file's own header comment) and every state - success, empty,
 * error, partial (404 on a single read) - is reachable through a mocked
 * `apiFetch`. Mirrors `purchaseOrderService.test.ts`'s convention.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import * as chatbotDomainService from './chatbotDomainService';
import {
  createChatbotDomain,
  getChatbotDomain,
  getChatbotDomainPromptBlock,
  listChatbotDomains,
  updateChatbotDomain,
} from './chatbotDomainService';
import type { ChatbotDomainInput } from '../types/chatbotDomain.types';

function ok(body: unknown, status = 200) {
  return {
    ok: true,
    status,
    headers: { get: () => 'application/json' },
    json: async () => body,
  } as unknown as Response;
}
function fail(detail: string, status = 400) {
  return {
    ok: false,
    status,
    headers: { get: () => 'application/json' },
    json: async () => ({ detail }),
    text: async () => JSON.stringify({ detail }),
  } as unknown as Response;
}
function notFound() {
  return { ok: false, status: 404, headers: { get: () => 'application/json' } } as unknown as Response;
}

const ROW = {
  id: 'd-1',
  name: 'incoming',
  label: 'Incoming stock',
  intents: [],
  tools: [],
  primary_tool: null,
  escalation_team_code: null,
  switch_words: [],
  narrowing: {},
  takes_date_filter: false,
  reveal_key: null,
  supported: true,
  ladder: [],
  updated_at: '2026-09-01T09:00:00',
};

beforeEach(() => apiFetch.mockReset());

describe('chatbotDomainService', () => {
  it('list: success reads limit=200/sort=sort_order and returns the row array', async () => {
    apiFetch.mockResolvedValue(ok({ data: [ROW], pagination: { total: 1, page: 1, limit: 200 } }));
    const rows = await listChatbotDomains();
    expect(rows).toEqual([ROW]);
    const u = new URL(String(apiFetch.mock.calls[0][0]), 'http://x');
    expect(u.pathname).toBe('/api/v1/system/chatbot/domains');
    expect(u.searchParams.get('limit')).toBe('200');
    expect(u.searchParams.get('sort')).toBe('sort_order');
  });

  it('list: empty (empty catalog) returns []', async () => {
    apiFetch.mockResolvedValue(ok({ data: [], pagination: { total: 0, page: 1, limit: 200 } }));
    expect(await listChatbotDomains()).toEqual([]);
  });

  it('list: error surfaces extractApiError\'s message', async () => {
    apiFetch.mockResolvedValue(fail('DB unavailable', 500));
    await expect(listChatbotDomains()).rejects.toThrow('DB unavailable');
  });

  it('get: partial state - a 404 resolves to undefined, not a thrown error', async () => {
    apiFetch.mockResolvedValue(notFound());
    expect(await getChatbotDomain('missing')).toBeUndefined();
  });

  it('get: success returns the row', async () => {
    apiFetch.mockResolvedValue(ok(ROW));
    expect(await getChatbotDomain('d-1')).toEqual(ROW);
  });

  it('create: success posts the input and returns the created row', async () => {
    apiFetch.mockResolvedValue(ok(ROW, 201));
    const input: ChatbotDomainInput = { ...ROW };
    // @ts-expect-error id/updated_at are not part of the input type
    delete input.id;
    const created = await createChatbotDomain(input);
    expect(created).toEqual(ROW);
    expect(apiFetch.mock.calls[0][1]).toMatchObject({ method: 'POST' });
  });

  it('create: error (e.g. duplicate name) surfaces the detail message', async () => {
    apiFetch.mockResolvedValue(fail('a domain named "incoming" already exists', 409));
    await expect(
      createChatbotDomain({
        name: 'incoming',
        label: 'x',
        intents: [],
        tools: [],
        primary_tool: null,
        escalation_team_code: null,
        switch_words: [],
        narrowing: {},
        takes_date_filter: false,
        reveal_key: null,
        supported: true,
        ladder: [],
      }),
    ).rejects.toThrow('already exists');
  });

  it('update: success puts to the row id and returns the saved row', async () => {
    apiFetch.mockResolvedValue(ok(ROW));
    const saved = await updateChatbotDomain('d-1', { ...ROW });
    expect(saved).toEqual(ROW);
    expect(apiFetch.mock.calls[0][0]).toContain('/domains/d-1');
    expect(apiFetch.mock.calls[0][1]).toMatchObject({ method: 'PUT' });
  });

  it('prompt block: success returns the rendered block text', async () => {
    apiFetch.mockResolvedValue(ok({ block: 'DOMAIN incoming: ...' }));
    expect(await getChatbotDomainPromptBlock('d-1')).toBe('DOMAIN incoming: ...');
  });

  it('prompt block: empty (never published) falls back to an empty string, not undefined', async () => {
    apiFetch.mockResolvedValue(ok({ block: null }));
    expect(await getChatbotDomainPromptBlock('d-1')).toBe('');
  });

  it('prompt block: error surfaces the message', async () => {
    apiFetch.mockResolvedValue(fail('block not rendered yet', 404));
    await expect(getChatbotDomainPromptBlock('d-1')).rejects.toThrow('block not rendered yet');
  });

  it('no deleteChatbotDomain export - delete is a server-deferred pending action (D7), by design', () => {
    expect(
      (chatbotDomainService as unknown as Record<string, unknown>).deleteChatbotDomain,
    ).toBeUndefined();
  });
});
