import { describe, expect, it, vi } from 'vitest';
import { sendAIAssistantMessage } from './aiAssistantChatApi';

vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(async (_url: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(String(init.body)) : {};
    return {
      ok: true,
      async json() {
        return {
          id: 'conv-1',
          title: null,
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
          messages: [
            {
              id: 'm1',
              role: 'user',
              content: body.message,
              metadata_json: {},
              created_at: '2026-01-01T00:00:00Z',
            },
          ],
        };
      },
    } as Response;
  }),
}));

describe('sendAIAssistantMessage', () => {
  it('sends message payload and returns parsed conversation', async () => {
    const result = await sendAIAssistantMessage('hello', 'conv-1');
    expect(result.id).toBe('conv-1');
    expect(result.messages[0]?.content).toBe('hello');
  });
});
