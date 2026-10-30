import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import AgentConsole from './AgentConsole';
import { ActionRefusedError } from '../services/agentConsoleService';

const getAgentConversation = vi.fn();
const withdrawAgentStep = vi.fn();

vi.mock('../services/agentConsoleService', async () => {
  const actual = await vi.importActual<typeof import('../services/agentConsoleService')>(
    '../services/agentConsoleService',
  );
  return {
    ...actual,
    postAgentTurn: vi.fn(),
    newAgentConversation: vi.fn(),
    confirmAgentAction: vi.fn(),
    cancelAgentAction: vi.fn(),
    getAgentConversation: (...a: unknown[]) => getAgentConversation(...a),
    withdrawAgentStep: (...a: unknown[]) => withdrawAgentStep(...a),
  };
});

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('../../respond-contacts/services/respondContactOutboundService', () => ({
  getRespondContactsOutbound: vi.fn().mockResolvedValue({ data: [] }),
}));

const STORAGE_KEY = 'agent-console:last-contact';
const SUMMARY = 'Approve purchase request PR-1 for Example Trading. The requester and the dealer contact will be told.';

function conversation(step: Record<string, unknown>) {
  return {
    conversation_id: 'cv1',
    pending_action: null,
    turns: [
      {
        turn_id: 't1',
        text: 'approve PR-1',
        reply_text: 'I will make these changes when you confirm:\n1. ' + SUMMARY,
        status: 'done',
        created_at: '2026-10-30T09:00:00Z',
        actions: [
          {
            id: 'a1',
            status: 'executed',
            decided_at: '2026-10-30T09:01:00Z',
            decided_by_name: 'Agent User',
            steps: [{ summary: SUMMARY, status: 'done', error: null, changes: [], ...step }],
          },
        ],
      },
    ],
  };
}

// Naive UTC, as the server sends it.
const inAMinute = () => new Date(Date.now() + 60_000).toISOString().replace('Z', '');

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
  getAgentConversation.mockReset();
  withdrawAgentStep.mockReset();
});

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

describe('AgentConsole waiting changes', () => {
  it('a change waiting out its grace window shows the countdown and Undo', async () => {
    getAgentConversation.mockResolvedValue(
      conversation({ waiting: { commit_at: inAMinute(), window_seconds: 60 } }),
    );
    renderConsole();

    await screen.findByTestId('agent-step-waiting');
    expect(screen.getByRole('button', { name: /undo/i })).toBeTruthy();
  });

  it('a change that is not waiting shows no Undo', async () => {
    getAgentConversation.mockResolvedValue(conversation({ waiting: null }));
    renderConsole();

    await screen.findByTestId('agent-actions');
    expect(screen.queryByTestId('agent-step-waiting')).toBeNull();
    expect(screen.queryByRole('button', { name: /undo/i })).toBeNull();
  });

  it('Undo withdraws that step of that action, then reads the conversation again', async () => {
    getAgentConversation.mockResolvedValueOnce(
      conversation({ waiting: { commit_at: inAMinute(), window_seconds: 60 } }),
    );
    getAgentConversation.mockResolvedValue(
      conversation({ status: 'withdrawn', waiting: null }),
    );
    withdrawAgentStep.mockResolvedValue({
      action_id: 'a1',
      status: 'executed',
      reply_text: 'Withdrawn. Nothing was changed and nobody was told.',
      steps: [],
    });
    renderConsole();

    fireEvent.click(await screen.findByRole('button', { name: /undo/i }));

    await waitFor(() => expect(withdrawAgentStep).toHaveBeenCalledWith('ZZT-1', 'a1', 0));
    await waitFor(() => expect(screen.queryByTestId('agent-step-waiting')).toBeNull());
  });

  it('a refused withdraw shows the reason in words', async () => {
    getAgentConversation.mockResolvedValue(
      conversation({ waiting: { commit_at: inAMinute(), window_seconds: 60 } }),
    );
    withdrawAgentStep.mockRejectedValue(new ActionRefusedError('applied'));
    renderConsole();

    fireEvent.click(await screen.findByRole('button', { name: /undo/i }));

    expect(
      await screen.findByText('That change already applied, so it can no longer be withdrawn.'),
    ).toBeTruthy();
  });
});
