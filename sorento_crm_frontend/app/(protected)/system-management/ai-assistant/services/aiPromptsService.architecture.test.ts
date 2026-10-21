/**
 * CHAT-INDEX-VIZ: the Architecture tab reads the chatbot module's own read surface
 * (`/system/chatbot/prompts/...`), not the core prompts router, so the backend's chatbot
 * import boundary holds.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

import { getPromptArchitecture } from './aiPromptsService';

describe('getPromptArchitecture', () => {
  beforeEach(() => apiFetch.mockReset());

  it('calls the chatbot read surface for the version', async () => {
    apiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ version: 77 }),
    });
    await getPromptArchitecture('chatbot_semantic_parser', 77);
    expect(apiFetch).toHaveBeenCalledWith(
      '/api/v1/system/chatbot/prompts/chatbot_semantic_parser/versions/77/architecture',
    );
  });
});
