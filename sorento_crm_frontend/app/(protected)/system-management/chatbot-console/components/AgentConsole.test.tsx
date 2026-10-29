import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import AgentConsole from './AgentConsole';
import { AgentRefusedError } from '../services/agentConsoleService';

const postAgentTurn = vi.fn();
const getAgentConversation = vi.fn();
const newAgentConversation = vi.fn();

vi.mock('../services/agentConsoleService', async () => {
  const actual = await vi.importActual<typeof import('../services/agentConsoleService')>(
    '../services/agentConsoleService',
  );
  return {
    ...actual,
    postAgentTurn: (...a: unknown[]) => postAgentTurn(...a),
    getAgentConversation: (...a: unknown[]) => getAgentConversation(...a),
    newAgentConversation: (...a: unknown[]) => newAgentConversation(...a),
  };
});

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('../../respond-contacts/services/respondContactOutboundService', () => ({
  getRespondContactsOutbound: vi.fn().mockResolvedValue({ data: [] }),
}));

const STORAGE_KEY = 'agent-console:last-contact';

function renderConsole() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AgentConsole />
    </QueryClientProvider>,
  );
}

const emptyConversation = { conversation_id: 'cv1', turns: [] };

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ id: 'ZZT-1', label: 'Test Contact' }));
  postAgentTurn.mockReset();
  getAgentConversation.mockReset().mockResolvedValue(emptyConversation);
  newAgentConversation.mockReset().mockResolvedValue({ conversation_id: 'cv2' });
});

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

describe('AgentConsole', () => {
  it('sends a message, shows Working while it runs, then the reply with rounds and tool chips', async () => {
    let finish: (v: unknown) => void = () => {};
    postAgentTurn.mockReturnValue(new Promise((resolve) => (finish = resolve)));
    renderConsole();
    await waitFor(() => expect(getAgentConversation).toHaveBeenCalledWith('ZZT-1'));

    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'stock of SRTWT7445?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    expect(await screen.findByText('Working...')).toBeInTheDocument();
    expect(screen.getByText('stock of SRTWT7445?')).toBeInTheDocument();
    expect(screen.getByLabelText('Message')).toBeDisabled();
    expect(postAgentTurn).toHaveBeenCalledWith('ZZT-1', 'stock of SRTWT7445?');

    getAgentConversation.mockResolvedValue({
      conversation_id: 'cv1',
      turns: [
        {
          turn_id: 't1',
          text: 'stock of SRTWT7445?',
          reply_text: 'There are 12 units.',
          status: 'done',
          created_at: '2026-10-29T09:00:00Z',
        },
      ],
    });
    finish({
      turn_id: 't1',
      conversation_id: 'cv1',
      reply_text: 'There are 12 units.',
      status: 'limited',
      limit_hit: 'rounds',
      rounds: 2,
      usage: { prompt_tokens: 1, completion_tokens: 1, cached_tokens: 0, calls: 2 },
      tool_calls: [{ name: 'crm_inventory_stock_balance_list', status: 'ok', ms: 10 }],
    });

    expect(await screen.findByText('There are 12 units.')).toBeInTheDocument();
    expect(screen.queryByText('Working...')).not.toBeInTheDocument();
    const meta = await screen.findByTestId('agent-reply-meta');
    expect(meta).toHaveTextContent('2 rounds');
    expect(meta).toHaveTextContent('Stock balance: ok');
    expect(meta).toHaveTextContent('Stopped: rounds limit');
  });

  it('shows a refusal in plain words', async () => {
    postAgentTurn.mockRejectedValue(new AgentRefusedError('no_linked_user'));
    renderConsole();
    await waitFor(() => expect(getAgentConversation).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'hi' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('This contact has no linked active user.');
  });

  it('loads earlier turns of the conversation', async () => {
    getAgentConversation.mockResolvedValue({
      conversation_id: 'cv1',
      turns: [
        { turn_id: 't0', text: 'earlier question', reply_text: 'earlier answer', status: 'done', created_at: '2026-10-29T09:00:00Z' },
      ],
    });
    renderConsole();
    expect(await screen.findByText('earlier question')).toBeInTheDocument();
    expect(screen.getByText('earlier answer')).toBeInTheDocument();
  });

  it('New conversation starts one and reloads an empty thread', async () => {
    getAgentConversation.mockResolvedValueOnce({
      conversation_id: 'cv1',
      turns: [
        { turn_id: 't0', text: 'earlier question', reply_text: 'earlier answer', status: 'done', created_at: '2026-10-29T09:00:00Z' },
      ],
    });
    renderConsole();
    expect(await screen.findByText('earlier question')).toBeInTheDocument();

    getAgentConversation.mockResolvedValue({ conversation_id: 'cv2', turns: [] });
    fireEvent.click(screen.getByRole('button', { name: /new conversation/i }));

    await waitFor(() => expect(newAgentConversation).toHaveBeenCalledWith('ZZT-1'));
    await waitFor(() => expect(screen.queryByText('earlier question')).not.toBeInTheDocument());
  });

  it('cannot send without a contact', () => {
    window.localStorage.clear();
    renderConsole();
    expect(screen.getByLabelText('Message')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  });
});
