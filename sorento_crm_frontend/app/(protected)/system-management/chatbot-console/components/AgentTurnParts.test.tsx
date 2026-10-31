/**
 * The pieces of an agent bubble (moved out of the old AgentConsole so the one console imports them):
 * Steps and reasoning, reply meta chips, Confirm/Cancel, the grace countdown with Undo, the action badges and
 * change lines, and the decision outcome. Rendered directly; the console wiring is in
 * ChatbotConsole.oneThread.test.tsx and ChatbotConsole.agentCards.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, within, fireEvent, cleanup } from '@testing-library/react';

import {
  ActionOutcome,
  ActionsBlock,
  ProposalActions,
  ReplyMeta,
  StepsDisclosure,
} from './AgentTurnParts';

afterEach(() => cleanup());

const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}/;
// Naive UTC, as the server sends it.
const inAMinute = () => new Date(Date.now() + 60_000).toISOString().replace('Z', '');

const THOUGHT_1 = 'I need the stock balance before anything else.';
const THOUGHT_2 = 'The balance is back, so I can answer.';
const STEPS = {
  rounds: 2,
  prompt_tokens: 300,
  completion_tokens: 30,
  cached_tokens: 0,
  tool_calls: [
    { name: 'crm_inventory_stock_balance_list', status: 'ok', ms: 40, detail: 'Stock balance (query: ZZT1): 1 row', round: 1 },
  ],
  reasoning: [
    { round: 1, text: THOUGHT_1, final: false },
    { round: 2, text: THOUGHT_2, final: false },
  ],
};

function openSteps(steps = STEPS) {
  render(<StepsDisclosure steps={steps} />);
  const disclosure = screen.getByTestId('agent-steps');
  fireEvent.click(within(disclosure).getByRole('button', { name: 'Steps' }));
  return disclosure;
}

describe('StepsDisclosure', () => {
  it('is collapsed until asked for, then lists rounds and tokens', () => {
    render(
      <StepsDisclosure
        steps={{
          rounds: 3, prompt_tokens: 12345, completion_tokens: 67, cached_tokens: 0,
          tool_calls: [
            { name: 'crm_report_ask', status: 'ok', ms: 120 },
            { name: 'crm_resolve', status: 'empty', ms: 3 },
          ],
        }}
      />,
    );
    const steps = screen.getByTestId('agent-steps');
    const toggle = within(steps).getByRole('button', { name: 'Steps' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(steps).not.toHaveTextContent('3 rounds');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(steps).toHaveTextContent('3 rounds');
    expect(steps).toHaveTextContent('Tokens: 12,345 in, 67 out');
    expect(steps).toHaveTextContent('Sales report: ok (120 ms)');
    expect(steps).toHaveTextContent('Find names and codes: empty (3 ms)');
    expect(steps.textContent).not.toMatch(UUID);
  });

  it('shows a call detail in plain words, and a call without detail keeps the old line', () => {
    const disclosure = openSteps({
      rounds: 2, prompt_tokens: 100, completion_tokens: 20, cached_tokens: 0,
      tool_calls: [
        { name: 'crm_customer_asks_list', status: 'ok', ms: 20, detail: 'Your customer asks: 2 rows' },
        { name: 'crm_customer_ask_update', status: 'denied', ms: 3, detail: 'Change an ask: refused, that ask is not yours' },
        { name: 'crm_report_ask', status: 'ok', ms: 120 },
      ],
    } as never);
    expect(disclosure).toHaveTextContent('Your customer asks: 2 rows');
    expect(disclosure).toHaveTextContent('Change an ask: refused, that ask is not yours');
    expect(disclosure).toHaveTextContent('Sales report: ok (120 ms)');
    expect(disclosure.textContent).not.toMatch(UUID);
  });

  it('shows one collapsed Thinking per round, opened on demand', () => {
    const disclosure = openSteps();
    const first = within(disclosure).getByRole('button', { name: 'Thinking (round 1)' });
    const second = within(disclosure).getByRole('button', { name: 'Thinking (round 2)' });
    expect(first).toHaveAttribute('aria-expanded', 'false');
    expect(second).toHaveAttribute('aria-expanded', 'false');
    expect(disclosure).not.toHaveTextContent(THOUGHT_1);
    fireEvent.click(first);
    expect(disclosure).toHaveTextContent(THOUGHT_1);
    expect(disclosure).not.toHaveTextContent(THOUGHT_2);
  });

  it("puts a round's thinking before that round's tool calls", () => {
    const text = openSteps().textContent ?? '';
    const r1 = text.indexOf('Thinking (round 1)');
    const call = text.indexOf('Stock balance (query: ZZT1): 1 row');
    const r2 = text.indexOf('Thinking (round 2)');
    expect(r1).toBeGreaterThan(-1);
    expect(r1).toBeLessThan(call);
    expect(call).toBeLessThan(r2);
  });

  it("labels the forced final answer's thinking and puts it after the round's calls", () => {
    const disclosure = openSteps({
      ...STEPS,
      rounds: 1,
      reasoning: [
        { round: 1, text: THOUGHT_1, final: false },
        { round: 1, text: THOUGHT_2, final: true },
      ],
    });
    expect(within(disclosure).queryByRole('button', { name: 'Thinking (round 2)' })).toBeNull();
    const text = disclosure.textContent ?? '';
    const call = text.indexOf('Stock balance (query: ZZT1): 1 row');
    expect(text.indexOf('Thinking (round 1)')).toBeLessThan(call);
    expect(text.indexOf('Thinking (final answer)')).toBeGreaterThan(call);
  });

  it('keeps long reasoning wrapped inside the console', () => {
    const long = `${'word '.repeat(400)}end`;
    const disclosure = openSteps({ ...STEPS, reasoning: [{ round: 1, text: long, final: false }] });
    fireEvent.click(within(disclosure).getByRole('button', { name: 'Thinking (round 1)' }));
    const body = within(disclosure).getByTestId('agent-reasoning-text');
    expect(body.className).toMatch(/whitespace-pre-wrap/);
    expect(body.className).toMatch(/break-words/);
    expect(disclosure.className).toMatch(/break-words/);
  });

  it('an older turn without reasoning keeps the plain Steps list', () => {
    const disclosure = openSteps({
      rounds: 1, prompt_tokens: 10, completion_tokens: 1, cached_tokens: 0,
      tool_calls: [{ name: 'crm_inventory_stock_balance_list', status: 'ok', ms: 40, detail: 'Stock balance: 1 row' }],
    } as never);
    expect(within(disclosure).queryByRole('button', { name: /Thinking/ })).toBeNull();
    expect(disclosure).toHaveTextContent('Stock balance: 1 row');
  });
});

describe('ReplyMeta', () => {
  it('shows rounds, a chip per tool and why it stopped', () => {
    render(
      <ReplyMeta
        meta={{ rounds: 2, limit_hit: 'rounds', tool_calls: [{ name: 'crm_inventory_stock_balance_list', status: 'ok' }] }}
      />,
    );
    const meta = screen.getByTestId('agent-reply-meta');
    expect(meta).toHaveTextContent('2 rounds');
    expect(meta).toHaveTextContent('Stock balance: ok');
    expect(meta).toHaveTextContent('Stopped: rounds limit');
  });

  it('says 1 round for one and the time limit for seconds', () => {
    render(<ReplyMeta meta={{ rounds: 1, limit_hit: 'seconds', tool_calls: [{ name: 'crm_report_ask', status: 'ok' }] }} />);
    const meta = screen.getByTestId('agent-reply-meta');
    expect(meta).toHaveTextContent('1 round');
    expect(meta).not.toHaveTextContent('1 rounds');
    expect(meta).toHaveTextContent('Sales report: ok');
    expect(meta).toHaveTextContent('Stopped: time limit');
  });

  it('names the resolver "Find names and codes" and hides the answer and plan calls', () => {
    render(
      <ReplyMeta
        meta={{
          rounds: 2, limit_hit: null,
          tool_calls: [
            { name: 'crm_resolve', status: 'ok' },
            { name: 'crm_products_find', status: 'ok' },
            { name: 'crm_inventory_stock_balance_list', status: 'empty' },
            { name: 'plan', status: 'ok' },
            { name: 'answer', status: 'ok' },
          ],
        }}
      />,
    );
    const meta = screen.getByTestId('agent-reply-meta');
    expect(meta).toHaveTextContent('Find names and codes: ok');
    expect(meta).toHaveTextContent('Find products: ok');
    expect(meta).toHaveTextContent('Stock balance: empty');
    expect(meta).not.toHaveTextContent(/answer/i);
    expect(meta).not.toHaveTextContent(/plan/i);
  });
});

describe('ProposalActions', () => {
  const action = (lines: string[]) => ({ id: 'a1', turn_id: 't1', lines, expires_at: '2099-01-01T00:00:00Z' });

  it('labels Confirm by the number of changes', () => {
    const { rerender } = render(
      <ProposalActions action={action(['One', 'Two'])} busy={false} onConfirm={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.getByRole('button', { name: 'Confirm 2 changes' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled();
    rerender(<ProposalActions action={action(['One'])} busy={false} onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Confirm change' })).toBeInTheDocument();
  });

  it('disables both buttons while a decision runs, and calls back', () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    const { rerender } = render(
      <ProposalActions action={action(['One'])} busy={false} onConfirm={onConfirm} onCancel={onCancel} />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Confirm change' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onCancel).toHaveBeenCalledTimes(1);
    rerender(<ProposalActions action={action(['One'])} busy onConfirm={onConfirm} onCancel={onCancel} />);
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
  });
});

describe('ActionsBlock: what was changed survives a reload', () => {
  const executed = {
    id: 'a1', status: 'executed', decided_at: '2026-10-30T09:05:00Z', decided_by_name: 'Fake Admin',
    steps: [
      {
        summary: 'Mark done on the ask for SRTWT7445 from Fake Trading', status: 'done', error: null,
        changes: [
          { record: 'SRTWT7445 for Fake Trading', field: 'Status', before: 'Open', after: 'Done' },
          { record: 'SRTWT7445 for Fake Trading', field: 'Note', before: 'none', after: 'Called the customer' },
        ],
      },
    ],
  };
  const noop = { withdrawing: false, onWithdraw: vi.fn(), onExpire: vi.fn() };

  it('shows the status badge, each step summary and its Field: before -> after lines', () => {
    render(<ActionsBlock actions={[executed] as never} {...noop} />);
    const block = screen.getByTestId('agent-actions');
    expect(within(block).getByText('Done')).toBeInTheDocument();
    expect(block).toHaveTextContent('Mark done on the ask for SRTWT7445 from Fake Trading');
    expect(block).toHaveTextContent('Status: Open -> Done');
    expect(block).toHaveTextContent('Note: none -> Called the customer');
    expect(block.textContent).not.toMatch(UUID);
  });

  it('shows a partly done action with the failed step error', () => {
    render(
      <ActionsBlock
        actions={[
          {
            id: 'a2', status: 'partial', decided_at: null, decided_by_name: 'Fake Admin',
            steps: [
              executed.steps[0],
              { summary: 'Mark done on the ask for SRTWT7446', status: 'failed', error: 'Stock ask not found.', changes: [] },
            ],
          },
        ] as never}
        {...noop}
      />,
    );
    const block = screen.getByTestId('agent-actions');
    expect(within(block).getByText('Partly done')).toBeInTheDocument();
    expect(block).toHaveTextContent('Stock ask not found.');
    expect(block).toHaveTextContent('Status: Open -> Done');
  });

  it('shows a cancelled action as Cancelled with no change lines', () => {
    render(
      <ActionsBlock
        actions={[
          {
            id: 'a3', status: 'cancelled', decided_at: null, decided_by_name: 'Fake Admin',
            steps: [{ summary: 'Mark done on the ask for SRTWT7447', status: 'proposed', error: null, changes: [] }],
          },
        ] as never}
        {...noop}
      />,
    );
    const block = screen.getByTestId('agent-actions');
    expect(within(block).getByText('Cancelled')).toBeInTheDocument();
    expect(block.textContent).not.toContain('->');
  });

  it('a change that is not waiting shows no Undo; a waiting one shows the countdown and Undo', () => {
    const waiting = { commit_at: inAMinute(), window_seconds: 60 };
    const { rerender } = render(
      <ActionsBlock actions={[{ ...executed, steps: [{ ...executed.steps[0], waiting: null }] }] as never} {...noop} />,
    );
    expect(screen.queryByTestId('agent-step-waiting')).toBeNull();
    expect(screen.queryByRole('button', { name: /undo/i })).toBeNull();
    rerender(<ActionsBlock actions={[{ ...executed, steps: [{ ...executed.steps[0], waiting }] }] as never} {...noop} />);
    expect(screen.getByTestId('agent-step-waiting')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /undo/i })).toBeInTheDocument();
  });

  it('Undo on the second step withdraws step 1 of that action, not step 0', () => {
    const onWithdraw = vi.fn();
    render(
      <ActionsBlock
        actions={[
          {
            ...executed,
            steps: [
              { ...executed.steps[0], waiting: null },
              { summary: 'Reject sponsorship form SF-1.', status: 'done', error: null, changes: [], waiting: { commit_at: inAMinute(), window_seconds: 60 } },
            ],
          },
        ] as never}
        withdrawing={false}
        onWithdraw={onWithdraw}
        onExpire={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /undo/i }));
    expect(onWithdraw).toHaveBeenCalledWith('a1', 1);
  });
});

describe('ActionOutcome', () => {
  it('shows the outcome badge and the reply text', () => {
    render(
      <ActionOutcome
        outcome={{ action_id: 'a1', status: 'executed', reply_text: 'Done. I made these changes:\n1. Mark it done', steps: [] }}
      />,
    );
    const outcome = screen.getByTestId('agent-action-outcome');
    expect(outcome).toHaveTextContent('Done');
    expect(outcome).toHaveTextContent('Done. I made these changes:');
  });
});
