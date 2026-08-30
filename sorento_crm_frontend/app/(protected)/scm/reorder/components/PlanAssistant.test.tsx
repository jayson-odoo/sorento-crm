/**
 * SCM M8 - PlanAssistant (slice E / M8-F6). ONE conversational surface with a SINGLE
 * Ask input: the backend auto-decides whether a question needs a live market scan.
 * A grounded answer renders as prose; when a scanned signal maps onto plan lines the
 * chat response carries a CONFIRM-GATED per-line qty proposal rendered inline - nothing
 * changes until the user confirms a line, which fires a real /adjust override upstream.
 *   M8-E1 one surface · M8-E2 grounded answer · M8-F6 single input + auto-routed proposal
 *
 * The chat hook is mocked so the mutation is deterministic.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ActionProposal, MarketProposalResult } from '../types/explainer.types';

Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});

const chatMutateAsync = vi.fn();
vi.mock('../hooks/useExplainer', () => ({
  useRunChat: () => ({ mutateAsync: chatMutateAsync, isPending: false }),
}));

import { PlanAssistant } from './PlanAssistant';

const proposal: MarketProposalResult = {
  signal_summary: 'Ceramic prices trending +8% into Q4',
  source_url: 'https://example.test/report',
  sources: [
    { url: 'https://example.test/report', title: 'Ceramics Q4 outlook' },
    { url: 'https://data.test/index', title: null },
  ],
  lines: [
    { rec_id: 'rec-1', sku: 'CW-BASIN-450', product_name: 'Basin', old_qty: 100, new_qty: 140, unit_cost: 100, cash_impact_delta: 4000, reason: 'seasonal uplift' },
  ],
};

function renderAssistant(over: Partial<React.ComponentProps<typeof PlanAssistant>> = {}) {
  const onApplyProposalLine = vi.fn();
  const onApplyActions = vi.fn();
  render(
    <PlanAssistant
      runId="run-1"
      onApplyProposalLine={onApplyProposalLine}
      onApplyActions={onApplyActions}
      {...over}
    />,
  );
  return { onApplyProposalLine, onApplyActions };
}

beforeEach(() => {
  chatMutateAsync.mockReset();
});

describe('PlanAssistant - one surface, single Ask input (M8-E1 / M8-F6)', () => {
  it('renders a single Ask input with no separate Search market button and no tabs', () => {
    renderAssistant();
    expect(screen.getByLabelText('Ask the plan assistant')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Ask/i })).toBeInTheDocument();
    // the standalone market button is gone - the assistant auto-routes market search
    expect(screen.queryByRole('button', { name: /Search market/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
  });

  it('disables the composer when there is no run to ground on', () => {
    renderAssistant({ runId: null });
    expect(screen.getByLabelText('Ask the plan assistant')).toBeDisabled();
  });
});

describe('PlanAssistant - knowledge sources (demo-only, no network)', () => {
  it('is collapsed by default and expands to reveal the add controls + caption', () => {
    renderAssistant();
    // collapsed: subtle toggle, no controls yet
    const toggle = screen.getByRole('button', { name: /Add knowledge source/i });
    expect(screen.queryByRole('button', { name: /Add attachment/i })).toBeNull();
    fireEvent.click(toggle);
    expect(screen.getByRole('button', { name: /Add attachment/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Add link/i })).toBeInTheDocument();
    expect(screen.getByText(/Sources ground what the assistant crawls against/i)).toBeInTheDocument();
  });

  it('adds + removes a link chip from local state without any network call', () => {
    const fetchSpy = vi.fn();
    (globalThis as unknown as { fetch: unknown }).fetch = fetchSpy;
    renderAssistant();
    fireEvent.click(screen.getByRole('button', { name: /Add knowledge source/i }));
    fireEvent.change(screen.getByLabelText('Knowledge source URL'), {
      target: { value: 'https://sorento.test/spec.pdf' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Add link/i }));
    // chip renders
    expect(screen.getByText('https://sorento.test/spec.pdf')).toBeInTheDocument();
    // remove it
    fireEvent.click(screen.getByRole('button', { name: /Remove https:\/\/sorento.test\/spec.pdf/i }));
    expect(screen.queryByText('https://sorento.test/spec.pdf')).toBeNull();
    // purely local - nothing hit the network
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(chatMutateAsync).not.toHaveBeenCalled();
  });

  it('captures picked file names as removable chips', () => {
    renderAssistant();
    fireEvent.click(screen.getByRole('button', { name: /Add knowledge source/i }));
    const fileInput = screen.getByLabelText('Attach knowledge files') as HTMLInputElement;
    const file = new File(['x'], 'forecast-2026.pdf', { type: 'application/pdf' });
    fireEvent.change(fileInput, { target: { files: [file] } });
    expect(screen.getByText('forecast-2026.pdf')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Remove forecast-2026.pdf/i }));
    expect(screen.queryByText('forecast-2026.pdf')).toBeNull();
  });
});

describe('PlanAssistant - grounded answer (M8-E2)', () => {
  it('sends the question and renders the grounded assistant answer', async () => {
    chatMutateAsync.mockResolvedValue({ answer: 'The basin buy eats the most cash at RM 14,000.' });
    renderAssistant();
    fireEvent.change(screen.getByLabelText('Ask the plan assistant'), { target: { value: 'which buys eat the most cash' } });
    fireEvent.click(screen.getByRole('button', { name: /^Ask$/i }));
    // user bubble echoes the question
    expect(await screen.findByText('which buys eat the most cash')).toBeInTheDocument();
    // grounded assistant answer renders
    expect(await screen.findByText(/eats the most cash at RM 14,000/i)).toBeInTheDocument();
    expect(chatMutateAsync).toHaveBeenCalledWith(expect.objectContaining({ question: 'which buys eat the most cash' }));
  });
});

describe('PlanAssistant - auto-routed confirm-gated market bump (M8-F6 / M8-E5)', () => {
  it('renders the inline proposal card from the chat response and only lands the override on confirm', async () => {
    chatMutateAsync.mockResolvedValue({
      answer: 'Ceramic prices are trending up into Q4. I mapped that to one plan line - review below.',
      proposal,
    });
    const { onApplyProposalLine } = renderAssistant();
    fireEvent.change(screen.getByLabelText('Ask the plan assistant'), { target: { value: 'ceramic price trend' } });
    fireEvent.click(screen.getByRole('button', { name: /^Ask$/i }));

    // the trend answer + the proposal card render together; nothing applied yet
    expect(await screen.findByText(/trending up into Q4/i)).toBeInTheDocument();
    expect(await screen.findByText('CW-BASIN-450')).toBeInTheDocument();
    expect(screen.getByText('140')).toBeInTheDocument();
    expect(onApplyProposalLine).not.toHaveBeenCalled();

    // confirming the line fires the override with the bumped qty
    fireEvent.click(screen.getByRole('button', { name: 'Confirm suggestion' }));
    expect(onApplyProposalLine).toHaveBeenCalledWith(
      expect.objectContaining({ row_id: 'rec-1', new_qty: 140, reason: 'seasonal uplift' }),
    );
    // the line flips to Applied
    expect(await screen.findByText('Applied')).toBeInTheDocument();
  });

  it('answers a trend conversationally with no card when nothing maps to the plan', async () => {
    chatMutateAsync.mockResolvedValue({
      answer: 'I could not get a live market reading right now, but here is what the plan shows.',
      proposal: null,
    });
    renderAssistant();
    fireEvent.change(screen.getByLabelText('Ask the plan assistant'), { target: { value: 'market trend for basins' } });
    fireEvent.click(screen.getByRole('button', { name: /^Ask$/i }));
    expect(await screen.findByText(/could not get a live market reading/i)).toBeInTheDocument();
    // no proposal card
    expect(screen.queryByText('Include in plan?')).not.toBeInTheDocument();
  });

  it('renders an error bubble when the chat call fails (degrades gracefully)', async () => {
    chatMutateAsync.mockRejectedValue(new Error('Assistant unavailable'));
    renderAssistant();
    fireEvent.change(screen.getByLabelText('Ask the plan assistant'), { target: { value: 'trend' } });
    fireEvent.click(screen.getByRole('button', { name: /^Ask$/i }));
    expect(await screen.findByText(/Assistant unavailable/i)).toBeInTheDocument();
  });
});

describe('PlanAssistant - action pipeline: NL instruction -> Apply (M8-F16)', () => {
  const actionProposal: ActionProposal = {
    summary: 'Buy FT-B only; reject the rest.',
    lines: [
      { rec_id: 'rec-1', sku: 'FT-B', product_name: 'Faucet B', action: 'accept', current_qty: 100, new_qty: null, reason: 'customer wants it' },
      { rec_id: 'rec-2', sku: 'ST-L-PCT', product_name: 'Sink L', action: 'reject', current_qty: 40, new_qty: null, reason: 'not wanted' },
      { rec_id: 'rec-3', sku: 'FT-03', product_name: 'Faucet 03', action: 'adjust', current_qty: 606, new_qty: 684, reason: 'bump to MoQ' },
    ],
  };

  it('renders the action card from the chat response; Apply routes all kept lines through the decision handlers', async () => {
    chatMutateAsync.mockResolvedValue({
      answer: 'I propose buying FT-B, rejecting the rest and bumping FT-03. Review and Apply below.',
      action_proposal: actionProposal,
    });
    const { onApplyActions } = renderAssistant();
    fireEvent.change(screen.getByLabelText('Ask the plan assistant'), { target: { value: 'buy FT-B only, reject the rest, bump FT-03 to 684' } });
    fireEvent.click(screen.getByRole('button', { name: /^Ask$/i }));

    // the per-line decisions render; nothing applied until Apply is clicked
    expect(await screen.findByText('FT-B')).toBeInTheDocument();
    expect(screen.getByText('ST-L-PCT')).toBeInTheDocument();
    expect(screen.getByText('684')).toBeInTheDocument();
    expect(onApplyActions).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /Apply 3 actions/i }));
    expect(onApplyActions).toHaveBeenCalledTimes(1);
    const applied = onApplyActions.mock.calls[0][0];
    expect(applied).toHaveLength(3);
    expect(applied.map((l: { action: string }) => l.action)).toEqual(['accept', 'reject', 'adjust']);
    // the card flips to Applied
    expect(await screen.findByText('Applied')).toBeInTheDocument();
  });

  it('a dismissed line is excluded from Apply (confirm-gated per line)', async () => {
    chatMutateAsync.mockResolvedValue({ answer: 'Proposed changes below.', action_proposal: actionProposal });
    const { onApplyActions } = renderAssistant();
    fireEvent.change(screen.getByLabelText('Ask the plan assistant'), { target: { value: 'reject the rest' } });
    fireEvent.click(screen.getByRole('button', { name: /^Ask$/i }));

    // dismiss the ST-L-PCT reject line, then Apply the remaining two
    fireEvent.click(await screen.findByRole('button', { name: /Dismiss ST-L-PCT/i }));
    fireEvent.click(screen.getByRole('button', { name: /Apply 2 actions/i }));
    const applied = onApplyActions.mock.calls[0][0];
    expect(applied.map((l: { rec_id: string }) => l.rec_id)).toEqual(['rec-1', 'rec-3']);
  });

  it('answers with no action card when the response has no action proposal', async () => {
    chatMutateAsync.mockResolvedValue({ answer: 'The basin buy eats the most cash.', action_proposal: null });
    renderAssistant();
    fireEvent.change(screen.getByLabelText('Ask the plan assistant'), { target: { value: 'which buys eat the most cash' } });
    fireEvent.click(screen.getByRole('button', { name: /^Ask$/i }));
    expect(await screen.findByText(/eats the most cash/i)).toBeInTheDocument();
    expect(screen.queryByText('Apply to plan?')).not.toBeInTheDocument();
  });
});
