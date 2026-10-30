import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import AutoConsole from './AutoConsole';
import ChatbotConsoleTabs from './ChatbotConsoleTabs';
import { AgentRefusedError } from '../services/agentConsoleService';

const postAutoTurn = vi.fn();

vi.mock('../services/autoConsoleService', () => ({
  postAutoTurn: (...a: unknown[]) => postAutoTurn(...a),
}));

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('../../respond-contacts/services/respondContactOutboundService', () => ({
  getRespondContactsOutbound: vi.fn().mockResolvedValue({ data: [] }),
}));

// The tabs test only needs to know which pane is showing.
vi.mock('./ChatbotConsole', () => ({ default: () => <div data-testid="stub-bot" /> }));
vi.mock('./AgentConsole', () => ({ default: () => <div data-testid="stub-agent" /> }));

const CONTACT = JSON.stringify({ id: 'ZZT-1', label: 'Test Contact' });

function renderAuto() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AutoConsole />
    </QueryClientProvider>,
  );
}

function send(text: string) {
  fireEvent.change(screen.getByLabelText('Message'), { target: { value: text } });
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));
}

const botTurn = (over = {}) => ({
  route: { route: 'chat', reason: 'jev', score: 0.1, provider: 'jev', ms: 80, tokens_in: 100, detail: null },
  turn: {
    turn_id: 'tb1',
    branch_kind: 'business_query',
    reply_text: 'BOT-REPLY',
    quick_replies: [],
    send_messages: [],
    session_vars: { open_question: { kind: 'outstanding_detail' } },
    trace_summary: {},
    actions: null,
  },
  ...over,
});

const agentTurn = (over = {}) => ({
  route: { route: 'agent', reason: 'jev', score: 0.9, provider: 'jev', ms: 90, tokens_in: 120, detail: null },
  turn: {
    turn_id: 'ta1',
    conversation_id: 'cv1',
    reply_text: 'AGENT-REPLY',
    status: 'answered',
    limit_hit: null,
    rounds: 2,
    usage: { prompt_tokens: 10, completion_tokens: 5, cached_tokens: 0, calls: 2 },
    tool_calls: [{ name: 'crm_inventory_stock_balance_list', status: 'ok', ms: 10 }],
    steps: {
      rounds: 2,
      prompt_tokens: 10,
      completion_tokens: 5,
      cached_tokens: 0,
      tool_calls: [{ name: 'crm_inventory_stock_balance_list', status: 'ok', ms: 10 }],
    },
    pending_action: null,
  },
  ...over,
});

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  window.localStorage.setItem('auto-console:last-contact', CONTACT);
  window.localStorage.setItem('chatbot-console:last-contact', CONTACT);
  postAutoTurn.mockReset();
});

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

describe('ChatbotConsoleTabs', () => {
  it('has an Auto tab beside Bot and Agent, and it opens the Auto console', async () => {
    const user = userEvent.setup();
    render(<ChatbotConsoleTabs />);
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(['Bot', 'Agent', 'Auto']);
    expect(screen.getByTestId('stub-bot')).toBeInTheDocument();
    await user.click(screen.getByRole('tab', { name: 'Auto' }));
    expect(await screen.findByTestId('auto-console')).toBeInTheDocument();
  });
});

describe('AutoConsole', () => {
  it('cannot send without a contact', () => {
    window.localStorage.clear();
    renderAuto();
    expect(screen.getByLabelText('Message')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  });

  it('posts the contact, text, session_vars and a run_id, and shows Working while it runs', async () => {
    let finish: (v: unknown) => void = () => {};
    postAutoTurn.mockReturnValue(new Promise((resolve) => (finish = resolve)));
    renderAuto();
    send('stock of ABC123?');

    expect(await screen.findByText('Working...')).toBeInTheDocument();
    expect(screen.getByLabelText('Message')).toBeDisabled();
    expect(postAutoTurn).toHaveBeenCalledTimes(1);
    const body = postAutoTurn.mock.calls[0][0];
    expect(body.contact_respond_id).toBe('ZZT-1');
    expect(body.text).toBe('stock of ABC123?');
    expect(body.session_vars).toEqual({});
    expect(typeof body.run_id).toBe('string');
    expect(body.run_id.length).toBeGreaterThan(0);

    finish(botTurn());
    expect(await screen.findByText('BOT-REPLY')).toBeInTheDocument();
    expect(screen.queryByText('Working...')).not.toBeInTheDocument();
  });

  it('keeps the bot side session_vars and run_id for the next message', async () => {
    postAutoTurn.mockResolvedValueOnce(botTurn());
    renderAuto();
    send('first');
    await screen.findByText('BOT-REPLY');
    const first = postAutoTurn.mock.calls[0][0];

    postAutoTurn.mockResolvedValueOnce(botTurn());
    send('the second one');
    await waitFor(() => expect(postAutoTurn).toHaveBeenCalledTimes(2));
    const second = postAutoTurn.mock.calls[1][0];
    expect(second.session_vars).toEqual({ open_question: { kind: 'outstanding_detail' } });
    expect(second.run_id).toBe(first.run_id);
  });

  it('keeps the session_vars through an agent-side reply, which carries none', async () => {
    postAutoTurn.mockResolvedValueOnce(botTurn());
    renderAuto();
    send('first');
    await screen.findByText('BOT-REPLY');
    postAutoTurn.mockResolvedValueOnce(agentTurn());
    send('compare Q3 and Q4');
    await screen.findByText('AGENT-REPLY');
    postAutoTurn.mockResolvedValueOnce(botTurn());
    send('third');
    await waitFor(() => expect(postAutoTurn).toHaveBeenCalledTimes(3));
    expect(postAutoTurn.mock.calls[2][0].session_vars).toEqual({ open_question: { kind: 'outstanding_detail' } });
  });

  it('shows a Bot badge on a bot reply and an Agent badge on an agent reply', async () => {
    postAutoTurn.mockResolvedValueOnce(botTurn());
    renderAuto();
    send('one');
    await screen.findByText('BOT-REPLY');
    postAutoTurn.mockResolvedValueOnce(agentTurn());
    send('two');
    await screen.findByText('AGENT-REPLY');
    const badges = screen.getAllByTestId('auto-route-badge');
    expect(badges).toHaveLength(2);
    expect(badges[0]).toHaveTextContent('Bot');
    expect(badges[1]).toHaveTextContent('Agent');
    // A plain Jev verdict needs no reason words.
    expect(screen.queryByTestId('auto-route-reason')).not.toBeInTheDocument();
  });

  it.each([
    ['low_confidence', 'low confidence'],
    ['daily_cap', 'daily cap'],
    ['router_failed', 'router failed'],
    ['routing_off', 'routing off'],
    ['not_eligible', 'not eligible'],
  ])('says why when the reason is %s', async (reason, words) => {
    const decided = botTurn();
    decided.route = { ...decided.route, reason, score: null as unknown as number };
    postAutoTurn.mockResolvedValueOnce(decided);
    renderAuto();
    send('hello');
    await screen.findByText('BOT-REPLY');
    expect(screen.getByTestId('auto-route-badge')).toHaveTextContent('Bot');
    expect(screen.getByTestId('auto-route-reason')).toHaveTextContent(words);
  });

  it('shows an agent-side reply with its steps and tool chips like the Agent tab', async () => {
    postAutoTurn.mockResolvedValueOnce(agentTurn());
    renderAuto();
    send('compare');
    await screen.findByText('AGENT-REPLY');
    expect(screen.getByTestId('agent-reply-meta')).toHaveTextContent('2 rounds');
    expect(screen.getByTestId('agent-reply-meta')).toHaveTextContent('Stock balance: ok');
    expect(screen.getByTestId('agent-steps')).toBeInTheDocument();
  });

  it('shows a proposal waiting for Confirm on an agent-side reply', async () => {
    const proposed = agentTurn();
    (proposed.turn as Record<string, unknown>).pending_action = {
      id: 'a1',
      turn_id: 'ta1',
      lines: ['Mark ask done'],
      expires_at: '2099-01-01T00:00:00Z',
    };
    postAutoTurn.mockResolvedValueOnce(proposed);
    renderAuto();
    send('mark the ask done');
    await screen.findByText('AGENT-REPLY');
    const box = screen.getByTestId('agent-proposal');
    // The lines are in the reply text, not repeated in the box.
    expect(within(box).queryByText('Mark ask done')).not.toBeInTheDocument();
    expect(within(box).getByRole('button', { name: /confirm/i })).toBeInTheDocument();
  });

  it('a bot-side reply has no agent steps', async () => {
    postAutoTurn.mockResolvedValueOnce(botTurn());
    renderAuto();
    send('hi');
    await screen.findByText('BOT-REPLY');
    expect(screen.queryByTestId('agent-steps')).not.toBeInTheDocument();
    expect(screen.queryByTestId('agent-reply-meta')).not.toBeInTheDocument();
  });

  it('shows a 409 refusal in plain words', async () => {
    postAutoTurn.mockRejectedValue(new AgentRefusedError('agent_busy'));
    renderAuto();
    send('hi');
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The agent is still working on another message for this contact.',
    );
  });

  it('shows any other failure as its message', async () => {
    postAutoTurn.mockRejectedValue(new Error('Something broke'));
    renderAuto();
    send('hi');
    expect(await screen.findByRole('alert')).toHaveTextContent('Something broke');
  });
});
