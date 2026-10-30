import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup, within } from '@testing-library/react';
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

  it('shows a loading state, then an empty state with a heading and a hint', async () => {
    let finish: (v: unknown) => void = () => {};
    getAgentConversation.mockReturnValue(new Promise((resolve) => (finish = resolve)));
    renderConsole();
    expect(await screen.findByRole('status', { name: 'Loading the conversation' })).toBeInTheDocument();
    expect(screen.queryByTestId('agent-console-empty')).not.toBeInTheDocument();

    finish({ conversation_id: null, turns: [] });
    const empty = await screen.findByTestId('agent-console-empty');
    expect(empty).toHaveTextContent('No messages yet');
    expect(empty.querySelector('button')).toBeNull();
  });

  it('renders rounds, tool chips and the stop reason on reloaded history', async () => {
    getAgentConversation.mockResolvedValue({
      conversation_id: 'cv1',
      turns: [
        {
          turn_id: 't0',
          text: 'old question',
          reply_text: 'old answer',
          status: 'done',
          created_at: '2026-10-29T09:00:00Z',
          rounds: 3,
          limit_hit: 'seconds',
          tool_calls: [{ name: 'crm_report_ask', status: 'ok' }],
        },
      ],
    });
    renderConsole();
    const meta = await screen.findByTestId('agent-reply-meta');
    expect(meta).toHaveTextContent('3 rounds');
    expect(meta).toHaveTextContent('Sales report: ok');
    expect(meta).toHaveTextContent('Stopped: time limit');
  });

  it('tells a refused contact in words when the conversation will not load', async () => {
    getAgentConversation.mockRejectedValue(new AgentRefusedError('switch_off'));
    renderConsole();
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Agent mode is off for this contact (Contact Details > Chatbot).',
    );
    expect(screen.queryByTestId('agent-console-empty')).not.toBeInTheDocument();
  });

  it('shows the resolver as "Find names and codes" and hides the answer call', async () => {
    getAgentConversation.mockResolvedValue({
      conversation_id: 'cv1',
      turns: [
        {
          turn_id: 't0',
          text: 'q',
          reply_text: 'a',
          status: 'done',
          created_at: '2026-10-29T09:00:00Z',
          rounds: 2,
          limit_hit: null,
          tool_calls: [
            { name: 'crm_resolve', status: 'ok' },
            { name: 'crm_products_find', status: 'ok' },
            { name: 'crm_inventory_stock_balance_list', status: 'empty' },
            { name: 'plan', status: 'ok' },
            { name: 'answer', status: 'ok' },
          ],
        },
      ],
    });
    renderConsole();
    const meta = await screen.findByTestId('agent-reply-meta');
    expect(meta).toHaveTextContent('Find names and codes: ok');
    expect(meta).toHaveTextContent('Find products: ok');
    expect(meta).toHaveTextContent('Stock balance: empty');
    expect(meta).not.toHaveTextContent(/answer/i);
    expect(meta).not.toHaveTextContent(/plan/i);
  });

  it('shows a collapsed Steps disclosure on a reloaded turn and lists the steps when opened', async () => {
    getAgentConversation.mockResolvedValue({
      conversation_id: 'cv1',
      turns: [
        {
          turn_id: 't0',
          text: 'q',
          reply_text: 'a',
          status: 'done',
          created_at: '2026-10-29T09:00:00Z',
          steps: {
            rounds: 3,
            prompt_tokens: 12345,
            completion_tokens: 67,
            cached_tokens: 0,
            tool_calls: [
              { name: 'crm_report_ask', status: 'ok', ms: 120 },
              { name: 'crm_resolve', status: 'empty', ms: 3 },
            ],
          },
        },
      ],
    });
    renderConsole();
    const steps = await screen.findByTestId('agent-steps');
    const toggle = within(steps).getByRole('button', { name: 'Steps' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(steps).not.toHaveTextContent('3 rounds');

    fireEvent.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(steps).toHaveTextContent('3 rounds');
    expect(steps).toHaveTextContent('Tokens: 12,345 in, 67 out');
    expect(steps).toHaveTextContent('Sales report: ok (120 ms)');
    expect(steps).toHaveTextContent('Find names and codes: empty (3 ms)');
    expect(steps.textContent).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}/);
  });

  it('has no Steps disclosure for a turn that stored none', async () => {
    getAgentConversation.mockResolvedValue({
      conversation_id: 'cv1',
      turns: [
        { turn_id: 't0', text: 'q', reply_text: 'a', status: 'done', created_at: '2026-10-29T09:00:00Z' },
      ],
    });
    renderConsole();
    expect(await screen.findByText('a')).toBeInTheDocument();
    expect(screen.queryByTestId('agent-steps')).not.toBeInTheDocument();
  });
});
