import { describe, expect, it, vi } from 'vitest';
import { sendAIAssistantMessage } from './aiAssistantChatApi';

let lastBody: Record<string, unknown> = {};

vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(async (_url: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(String(init.body)) : {};
    lastBody = body;
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

  it('omits confirm_action on a normal turn', async () => {
    await sendAIAssistantMessage('hello', 'conv-1');
    expect(lastBody.confirm_action).toBeNull();
  });

  it('passes confirm_action through for a write confirmation', async () => {
    await sendAIAssistantMessage('Confirm', 'conv-1', null, 'confirm');
    expect(lastBody.confirm_action).toBe('confirm');
    await sendAIAssistantMessage('Cancel', 'conv-1', null, 'cancel');
    expect(lastBody.confirm_action).toBe('cancel');
  });
});
