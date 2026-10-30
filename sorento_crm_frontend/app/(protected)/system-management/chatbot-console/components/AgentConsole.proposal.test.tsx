import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import AgentConsole from './AgentConsole';
import { ActionRefusedError } from '../services/agentConsoleService';

const postAgentTurn = vi.fn();
const getAgentConversation = vi.fn();
const newAgentConversation = vi.fn();
const confirmAgentAction = vi.fn();
const cancelAgentAction = vi.fn();

vi.mock('../services/agentConsoleService', async () => {
  const actual = await vi.importActual<typeof import('../services/agentConsoleService')>(
    '../services/agentConsoleService',
  );
  return {
    ...actual,
    postAgentTurn: (...a: unknown[]) => postAgentTurn(...a),
    getAgentConversation: (...a: unknown[]) => getAgentConversation(...a),
    newAgentConversation: (...a: unknown[]) => newAgentConversation(...a),
    confirmAgentAction: (...a: unknown[]) => confirmAgentAction(...a),
    cancelAgentAction: (...a: unknown[]) => cancelAgentAction(...a),
  };
});

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('../../respond-contacts/services/respondContactOutboundService', () => ({
  getRespondContactsOutbound: vi.fn().mockResolvedValue({ data: [] }),
}));

const STORAGE_KEY = 'agent-console:last-contact';
const REPLY =
  'I will make these changes when you confirm:\n1. Mark ask SRTWT7445 done\n2. Mark ask SRTWT7446 done\nReply yes to go ahead, or tell me what to change.';

const proposed = {
  conversation_id: 'cv1',
  turns: [
    {
      turn_id: 't1',
      text: 'mark both asks done',
      reply_text: REPLY,
      status: 'done',
      created_at: '2026-10-30T09:00:00Z',
    },
  ],
  pending_action: {
    id: 'a1',
    turn_id: 't1',
    lines: ['Mark ask SRTWT7445 done', 'Mark ask SRTWT7446 done'],
    expires_at: '2026-10-30T09:10:00Z',
  },
};
const decided = { ...proposed, pending_action: null };

function renderConsole() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AgentConsole />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ id: 'ZZT-1', label: 'Test Contact' }));
  postAgentTurn.mockReset();
  newAgentConversation.mockReset();
  getAgentConversation.mockReset().mockResolvedValue(proposed);
  confirmAgentAction.mockReset();
  cancelAgentAction.mockReset();
});

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

describe('AgentConsole proposals', () => {
  it('shows Confirm and Cancel under the reply that proposed the changes', async () => {
    renderConsole();
    expect(await screen.findByTestId('agent-proposal')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm 2 changes' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled();
  });

  it('shows no buttons when nothing is pending', async () => {
    getAgentConversation.mockResolvedValue(decided);
    renderConsole();
    await screen.findByText('mark both asks done');
    expect(screen.queryByTestId('agent-proposal')).not.toBeInTheDocument();
  });

  it('Confirm calls the service, then shows the result and drops the buttons', async () => {
    let finish: (v: unknown) => void = () => {};
    confirmAgentAction.mockReturnValue(new Promise((resolve) => (finish = resolve)));
    renderConsole();
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm 2 changes' }));

    await waitFor(() => expect(confirmAgentAction).toHaveBeenCalledWith('ZZT-1', 'a1'));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled());

    getAgentConversation.mockResolvedValue(decided);
    finish({
      action_id: 'a1',
      status: 'executed',
      reply_text: 'Done. I made these changes:\n1. Mark ask SRTWT7445 done\n2. Mark ask SRTWT7446 done',
      steps: [],
    });

    const outcome = await screen.findByTestId('agent-action-outcome');
    expect(outcome).toHaveTextContent('Done');
    expect(outcome).toHaveTextContent('Done. I made these changes:');
    await waitFor(() => expect(screen.queryByTestId('agent-proposal')).not.toBeInTheDocument());
  });

  it('Cancel calls the service and shows Cancelled', async () => {
    cancelAgentAction.mockResolvedValue({
      action_id: 'a1',
      status: 'cancelled',
      reply_text: 'Cancelled. Nothing was changed.',
      steps: [],
    });
    renderConsole();
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));
    getAgentConversation.mockResolvedValue(decided);

    await waitFor(() => expect(cancelAgentAction).toHaveBeenCalledWith('ZZT-1', 'a1'));
    expect(await screen.findByText('Cancelled. Nothing was changed.')).toBeInTheDocument();
  });

  it('a refused decision shows the reason in words', async () => {
    confirmAgentAction.mockRejectedValue(new ActionRefusedError('expired'));
    renderConsole();
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm 2 changes' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This proposal expired. Ask again to get a fresh one.',
    );
  });

  it('one change reads Confirm change', async () => {
    getAgentConversation.mockResolvedValue({
      ...proposed,
      pending_action: { ...proposed.pending_action, lines: ['Mark ask SRTWT7445 done'] },
    });
    renderConsole();
    expect(await screen.findByRole('button', { name: 'Confirm change' })).toBeInTheDocument();
  });
});
