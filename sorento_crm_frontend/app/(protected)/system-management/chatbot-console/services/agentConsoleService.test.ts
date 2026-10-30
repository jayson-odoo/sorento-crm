import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

import {
  AgentRefusedError,
  getAgentConversation,
  newAgentConversation,
  postAgentTurn,
} from './agentConsoleService';

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

beforeEach(() => apiFetch.mockReset());

describe('agentConsoleService', () => {
  it('posts a turn with the contact and text', async () => {
    apiFetch.mockResolvedValueOnce(json({ reply_text: 'ok', turn_id: 't1' }));
    const result = await postAgentTurn('C1', 'stock?');
    expect(apiFetch.mock.calls[0][0]).toBe('/api/v1/system/chatbot/agent/turn');
    expect(apiFetch.mock.calls[0][1].method).toBe('POST');
    expect(JSON.parse(apiFetch.mock.calls[0][1].body)).toEqual({
      contact_respond_id: 'C1',
      text: 'stock?',
    });
    expect(result.reply_text).toBe('ok');
  });

  it('turns a 409 refusal into an AgentRefusedError with plain words', async () => {
    apiFetch.mockResolvedValueOnce(
      json({ detail: { code: 'agent_refused', reason: 'switch_off' } }, 409),
    );
    const error = await postAgentTurn('C1', 'x').catch((e) => e);
    expect(error).toBeInstanceOf(AgentRefusedError);
    expect(error.reason).toBe('switch_off');
    expect(error.message).toBe('Agent mode is off for this contact (Contact Details > Chatbot).');
  });

  it('extracts the API error for any other failure', async () => {
    apiFetch.mockResolvedValueOnce(json({ detail: 'Something broke' }, 500));
    await expect(postAgentTurn('C1', 'x')).rejects.toThrow('Something broke');
  });

  it('loads the conversation with the contact as a query parameter', async () => {
    apiFetch.mockResolvedValueOnce(json({ conversation_id: 'cv', turns: [] }));
    const result = await getAgentConversation('C 1');
    expect(apiFetch.mock.calls[0][0]).toBe(
      '/api/v1/system/chatbot/agent/conversation?contact_respond_id=C+1',
    );
    expect(result.turns).toEqual([]);
  });

  it('starts a new conversation', async () => {
    apiFetch.mockResolvedValueOnce(json({ conversation_id: 'cv2' }));
    await newAgentConversation('C1');
    expect(apiFetch.mock.calls[0][0]).toBe('/api/v1/system/chatbot/agent/conversation/new');
    expect(JSON.parse(apiFetch.mock.calls[0][1].body)).toEqual({ contact_respond_id: 'C1' });
  });

  it('extracts the error when the conversation fails to load', async () => {
    apiFetch.mockResolvedValueOnce(json({ detail: 'No access' }, 403));
    await expect(getAgentConversation('C1')).rejects.toThrow('No access');
  });

  it('turns a busy 409 into an AgentRefusedError', async () => {
    apiFetch.mockResolvedValueOnce(json({ detail: { code: 'agent_busy' } }, 409));
    const error = await postAgentTurn('C1', 'x').catch((e) => e);
    expect(error).toBeInstanceOf(AgentRefusedError);
    expect(error.message).toBe('The agent is still working on another message for this contact.');
  });

  it('turns a 409 refusal on the conversation routes into the same error', async () => {
    apiFetch.mockResolvedValueOnce(
      json({ detail: { code: 'agent_refused', reason: 'no_linked_user' } }, 409),
    );
    await expect(getAgentConversation('C1')).rejects.toBeInstanceOf(AgentRefusedError);
    apiFetch.mockResolvedValueOnce(
      json({ detail: { code: 'agent_refused', reason: 'switch_off' } }, 409),
    );
    await expect(newAgentConversation('C1')).rejects.toBeInstanceOf(AgentRefusedError);
  });
});
