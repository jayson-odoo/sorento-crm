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

describe('agentConsoleService actions', () => {
  it('confirms an action for the contact', async () => {
    const { confirmAgentAction } = await import('./agentConsoleService');
    apiFetch.mockResolvedValueOnce(json({ action_id: 'a1', status: 'executed', reply_text: 'Done.', steps: [] }));
    const result = await confirmAgentAction('C1', 'a1');
    expect(apiFetch.mock.calls[0][0]).toBe('/api/v1/system/chatbot/agent/actions/a1/confirm');
    expect(apiFetch.mock.calls[0][1].method).toBe('POST');
    expect(JSON.parse(apiFetch.mock.calls[0][1].body)).toEqual({ contact_respond_id: 'C1' });
    expect(result.status).toBe('executed');
  });

  it('cancels an action for the contact', async () => {
    const { cancelAgentAction } = await import('./agentConsoleService');
    apiFetch.mockResolvedValueOnce(json({ action_id: 'a1', status: 'cancelled', reply_text: 'x', steps: [] }));
    await cancelAgentAction('C1', 'a1');
    expect(apiFetch.mock.calls[0][0]).toBe('/api/v1/system/chatbot/agent/actions/a1/cancel');
  });

  it('turns a 409 action refusal into an ActionRefusedError with plain words', async () => {
    const { ActionRefusedError, confirmAgentAction } = await import('./agentConsoleService');
    apiFetch.mockResolvedValueOnce(json({ detail: { code: 'action_refused', reason: 'not_proposed' } }, 409));
    const error = await confirmAgentAction('C1', 'a1').catch((e) => e);
    expect(error).toBeInstanceOf(ActionRefusedError);
    expect(error.reason).toBe('not_proposed');
    expect(error.message).toBe('This proposal was already decided.');
  });

  it('withdraws one waiting step of an action for the contact', async () => {
    const { withdrawAgentStep } = await import('./agentConsoleService');
    apiFetch.mockResolvedValueOnce(json({ action_id: 'a1', status: 'executed', reply_text: 'Withdrawn.', steps: [] }));
    await withdrawAgentStep('C1', 'a1', 2);
    expect(apiFetch.mock.calls[0][0]).toBe('/api/v1/system/chatbot/agent/actions/a1/steps/2/withdraw');
    expect(apiFetch.mock.calls[0][1].method).toBe('POST');
    expect(JSON.parse(apiFetch.mock.calls[0][1].body)).toEqual({ contact_respond_id: 'C1' });
  });

  it('a withdraw refused because the change applied reads in plain words', async () => {
    const { ActionRefusedError, withdrawAgentStep } = await import('./agentConsoleService');
    apiFetch.mockResolvedValueOnce(json({ detail: { code: 'action_refused', reason: 'applied' } }, 409));
    const error = await withdrawAgentStep('C1', 'a1', 0).catch((e) => e);
    expect(error).toBeInstanceOf(ActionRefusedError);
    expect(error.message).toBe('That change already applied, so it can no longer be withdrawn.');
  });
});
