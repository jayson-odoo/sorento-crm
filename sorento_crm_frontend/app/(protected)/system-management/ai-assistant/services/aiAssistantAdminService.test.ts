import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

import { updateAIAssistantConfig } from './aiAssistantAdminService';

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const payload = {
  provider: 'openai',
  model: 'gpt-4o-mini',
  temperature: 0,
  system_prompt: '',
  enabled_tools: [],
  rag_enabled: true,
  is_enabled: true,
};

beforeEach(() => apiFetch.mockReset());

describe('updateAIAssistantConfig', () => {
  it("shows the server's message when the save is refused", async () => {
    apiFetch.mockResolvedValueOnce(
      json({ message: 'The Jev API key must use plain ASCII characters.' }, 400),
    );
    await expect(updateAIAssistantConfig(payload)).rejects.toThrow(
      'The Jev API key must use plain ASCII characters.',
    );
  });

  it('falls back to the generic sentence when the body says nothing', async () => {
    apiFetch.mockResolvedValueOnce(new Response('', { status: 400 }));
    await expect(updateAIAssistantConfig(payload)).rejects.toThrow('Failed to update AI assistant config');
  });
});
