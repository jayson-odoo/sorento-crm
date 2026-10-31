import { describe, expect, it, vi } from 'vitest';
import { apiFetch } from '@/lib/api';
import {
  cancelPanelAction,
  confirmPanelAction,
  sendAIAssistantMessage,
  withdrawPanelStep,
} from './aiAssistantChatApi';

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

// AGENTIC-UNIFY PR 3, slice 4 (red): the panel's three action calls (AC-22).
// Routes: POST /api/v1/system/ai-assistant/agent/actions/{id}/confirm | /cancel | /steps/{index}/withdraw.
// The user comes from the session, so no contact is sent. Failures throw the server's own message.
describe('panel action calls', () => {
  const BASE = '/api/v1/system/ai-assistant/agent/actions';
  const outcome = { action_id: 'a1', status: 'executed', reply_text: 'Done.', steps: [] };
  const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
  const mocked = vi.mocked(apiFetch);

  function lastCall() {
    const [url, init] = mocked.mock.calls[mocked.mock.calls.length - 1] as [string, RequestInit | undefined];
    return { url, init, body: init?.body ? JSON.parse(String(init.body)) : {} };
  }

  it('confirms an action by POST to its confirm route and returns the outcome', async () => {
    mocked.mockResolvedValueOnce(json(outcome));
    const result = await confirmPanelAction('a1');
    const { url, init, body } = lastCall();
    expect(url).toBe(`${BASE}/a1/confirm`);
    expect(init?.method).toBe('POST');
    expect(body).toEqual({});
    expect(result.status).toBe('executed');
    expect(result.reply_text).toBe('Done.');
  });

  it('cancels an action by POST to its cancel route', async () => {
    mocked.mockResolvedValueOnce(json({ ...outcome, status: 'cancelled' }));
    const result = await cancelPanelAction('a1');
    const { url, init, body } = lastCall();
    expect(url).toBe(`${BASE}/a1/cancel`);
    expect(init?.method).toBe('POST');
    expect(body).toEqual({});
    expect(result.status).toBe('cancelled');
  });

  it('withdraws one step by POST to its withdraw route', async () => {
    mocked.mockResolvedValueOnce(json(outcome));
    await withdrawPanelStep('a1', 2);
    const { url, init, body } = lastCall();
    expect(url).toBe(`${BASE}/a1/steps/2/withdraw`);
    expect(init?.method).toBe('POST');
    expect(body).toEqual({});
  });

  it('encodes the action id in the path', async () => {
    mocked.mockResolvedValueOnce(json(outcome));
    await confirmPanelAction('a/1 ?x');
    expect(lastCall().url).toBe(`${BASE}/${encodeURIComponent('a/1 ?x')}/confirm`);
  });

  it('sends no contact in any body', async () => {
    mocked.mockResolvedValueOnce(json(outcome)).mockResolvedValueOnce(json(outcome)).mockResolvedValueOnce(json(outcome));
    await confirmPanelAction('a1');
    expect(JSON.stringify(lastCall().body)).not.toContain('contact');
    await cancelPanelAction('a1');
    expect(JSON.stringify(lastCall().body)).not.toContain('contact');
    await withdrawPanelStep('a1', 0);
    expect(JSON.stringify(lastCall().body)).not.toContain('contact');
  });

  it.each([
    ['confirm', () => confirmPanelAction('a1')],
    ['cancel', () => cancelPanelAction('a1')],
    ['withdraw', () => withdrawPanelStep('a1', 0)],
  ])('throws the server message when %s fails', async (_name, call) => {
    mocked.mockResolvedValueOnce(json({ detail: 'This proposal was already decided.' }, 409));
    await expect(call()).rejects.toThrow('This proposal was already decided.');
  });
});
