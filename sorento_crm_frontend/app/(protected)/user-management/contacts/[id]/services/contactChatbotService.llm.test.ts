/**
 * MODEL-PER-CONTACT AC-M-3 (FE side): the contact chatbot PUT body carries `llm` only when the
 * operator touched it. Absent = not sent; null = clear; {provider, model} = set. The response's
 * `chatbot_llm` reaches the profile unchanged.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { saveContactChatbotProfile } from './contactChatbotService';

function ok(body: unknown) {
  return { ok: true, headers: { get: () => 'application/json' }, json: async () => body } as unknown as Response;
}

const INPUT = {
  chatbot_memory_level: null,
  tier: null,
  default_ledgers: [],
  stock_allowed: true,
  notify_salesman: false,
  packing_list_allowed: false,
  eta_offset_applied: true,
  escalation_allowed: true,
  chatbot_allowed: true,
  skip_period_questions: false,
  files_as_links: false,
};

const sentBody = () => JSON.parse((apiFetch.mock.calls[0][1] as RequestInit).body as string);

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockResolvedValue(ok({ id: 'c1' }));
});

describe('saveContactChatbotProfile - llm', () => {
  it('sends no llm key when the operator did not touch it', async () => {
    await saveContactChatbotProfile('c1', INPUT);
    expect(sentBody()).not.toHaveProperty('llm');
  });

  it('sends llm: {provider, model} when set', async () => {
    await saveContactChatbotProfile('c1', { ...INPUT, llm: { provider: 'gemini', model: 'gemini-3.5-flash-lite' } } as never);
    expect(sentBody().llm).toEqual({ provider: 'gemini', model: 'gemini-3.5-flash-lite' });
  });

  it('sends llm: null when cleared', async () => {
    await saveContactChatbotProfile('c1', { ...INPUT, llm: null } as never);
    expect(sentBody()).toHaveProperty('llm', null);
  });

  it('does not turn the read-side chatbot_llm into a write', async () => {
    const withRead = { ...INPUT, chatbot_llm: { provider: 'openai', model: 'gpt-4.1', source: 'tag', tags: ['A'] } };
    await saveContactChatbotProfile('c1', withRead as never);
    expect(sentBody()).not.toHaveProperty('llm');
    expect(sentBody()).not.toHaveProperty('chatbot_llm');
  });

  it('carries the response chatbot_llm onto the returned profile', async () => {
    const chatbot_llm = { provider: 'gemini', model: 'g', source: 'tag', tags: ['Office Staff'] };
    apiFetch.mockResolvedValue(ok({ id: 'c1', chatbot_llm }));
    const profile = (await saveContactChatbotProfile('c1', INPUT)) as unknown as { chatbot_llm: unknown };
    expect(profile.chatbot_llm).toEqual(chatbot_llm);
  });
});
