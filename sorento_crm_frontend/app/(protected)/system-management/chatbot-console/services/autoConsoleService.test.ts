import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

import { AgentRefusedError } from './agentConsoleService';
import { postAutoTurn } from './autoConsoleService';

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const body = { contact_respond_id: 'C1', text: 'compare Q3 and Q4', session_vars: { focus: null }, run_id: 'console-r1' };

beforeEach(() => apiFetch.mockReset());

describe('autoConsoleService', () => {
  it('posts contact, text, session_vars and run_id to auto-turn and returns the body', async () => {
    const reply = { route: { route: 'agent', reason: 'jev', score: 0.9 }, turn: { reply_text: 'ok' } };
    apiFetch.mockResolvedValueOnce(json(reply));
    const result = await postAutoTurn(body);
    expect(apiFetch.mock.calls[0][0]).toBe('/api/v1/system/chatbot/console/auto-turn');
    expect(apiFetch.mock.calls[0][1].method).toBe('POST');
    expect(JSON.parse(apiFetch.mock.calls[0][1].body)).toEqual(body);
    expect(result).toEqual(reply);
  });

  it('turns a 409 agent_refused into an AgentRefusedError with plain words', async () => {
    apiFetch.mockResolvedValueOnce(json({ detail: { code: 'agent_refused', reason: 'switch_off' } }, 409));
    const error = await postAutoTurn(body).catch((e) => e);
    expect(error).toBeInstanceOf(AgentRefusedError);
    expect(error.reason).toBe('switch_off');
    expect(error.message).toBe('Agent mode is off for this contact (Contact Details > Chatbot).');
  });

  it('turns a 409 agent_busy into an AgentRefusedError', async () => {
    apiFetch.mockResolvedValueOnce(json({ detail: { code: 'agent_busy' } }, 409));
    const error = await postAutoTurn(body).catch((e) => e);
    expect(error).toBeInstanceOf(AgentRefusedError);
    expect(error.message).toBe('The agent is still working on another message for this contact.');
  });

  it('extracts the API error for any other failure', async () => {
    apiFetch.mockResolvedValueOnce(json({ detail: 'Something broke' }, 500));
    await expect(postAutoTurn(body)).rejects.toThrow('Something broke');
  });
});
