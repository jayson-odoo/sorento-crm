/**
 * SCM S5 - PlanExceptionReviewSheet (UAC Group D).
 *
 * The panel is where an exception becomes a decision that changes a supplier's placed
 * order, so what these pin is the set of refusals:
 *
 *   - **Reject without a reason is impossible** (AC-D6).
 *   - **Approve without choosing an action is impossible.** The first action is the
 *     engine's proposal, not a preselected inevitability.
 *   - **A split must be strictly inside the quantity** (AC-D11b), because the remainder is
 *     what stays on the original line and the two parts must sum to it.
 *   - **Before and after are both rendered** (AC-D4), and each reading signal names the
 *     field it came from (AC-D12) - a reviewer who cannot see the reasoning can only
 *     disagree with the outcome.
 *   - **A decided exception is read-only.** Re-deciding is a different operation, and
 *     silently overwriting loses who decided what.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { PlanExceptionReviewSheet } from './PlanExceptionReviewSheet';
import type { PlanException, ProposedAction } from '../types/planException.types';

function action(
  code: ProposedAction['code'],
  rank: number,
  over: Partial<ProposedAction> = {},
): ProposedAction {
  return {
    code,
    rank,
    rationale: `because ${code}`,
    candidate_so_number: null,
    candidate_need_by: null,
    candidate_warehouse_code: null,
    ...over,
  };
}

function exc(over: Partial<PlanException> = {}): PlanException {
  return {
    exception_id: 'exc-1',
    exception_type: 'supply_surplus',
    product_code: 'C-FH24',
    product_name: 'Ceramic FH24',
    uom: 'PCS',
    warehouse_code: 'WH3-AM',
    pool_code: 'WH3-AM',
    po_number: 'PO26-0398',
    po_expected_date: '2026-09-12',
    quantity: 240,
    timeline: {
      before_points: [
        { date: '2026-08-04', net: 120, label: null },
        { date: '2026-09-25', net: 120, label: 'SO26-0877 due' },
      ],
      after_points: [
        { date: '2026-08-04', net: 120, label: null },
        { date: '2026-09-25', net: 360, label: 'SO26-0877 deferred' },
      ],
      before_shortfall_at: null,
      after_shortfall_at: null,
      before_shortfall_qty: null,
      after_shortfall_qty: null,
    },
    reading: {
      lifecycle: { value: 'Active', source: 'products.is_discontinued' },
      velocity: { value: 'A / X', source: 'scm.item_classification' },
      business: { value: 'Project', source: 'market_segments.demand_class' },
      last_po: { value: '2026-06-19', source: 'purchase_orders.order_date' },
    },
    actions: [
      action('relink_so', 1, { candidate_so_number: 'SO26-0931', candidate_need_by: '2026-09-30' }),
      action('split', 2),
      action('accept', 3),
    ],
    status: 'open',
    decided_by: null,
    decided_at: null,
    decided_action: null,
    decision_reason: null,
    ...over,
  };
}

function renderSheet(over: Partial<PlanException> = {}, onDecide = vi.fn()) {
  render(
    <PlanExceptionReviewSheet
      exception={exc(over)}
      open
      onOpenChange={vi.fn()}
      onDecide={onDecide}
    />,
  );
  return onDecide;
}

beforeEach(() => vi.clearAllMocks());

describe('PlanExceptionReviewSheet', () => {
  it('renders both timelines, not only the new position', () => {
    renderSheet();
    expect(screen.getByText('Before')).toBeInTheDocument();
    expect(screen.getByText('After')).toBeInTheDocument();
    expect(screen.getByText('SO26-0877 due')).toBeInTheDocument();
    expect(screen.getByText('SO26-0877 deferred')).toBeInTheDocument();
  });

  it('names the source field of every reading signal', () => {
    renderSheet();
    expect(screen.getByText('products.is_discontinued')).toBeInTheDocument();
    expect(screen.getByText('scm.item_classification')).toBeInTheDocument();
    expect(screen.getByText('market_segments.demand_class')).toBeInTheDocument();
    expect(screen.getByText('purchase_orders.order_date')).toBeInTheDocument();
  });

  it('marks the first action as the proposal and carries its candidate order', () => {
    renderSheet();
    expect(screen.getByText('Proposed first')).toBeInTheDocument();
    expect(screen.getByText(/SO26-0931/)).toBeInTheDocument();
  });

  it('blocks approve until an action is chosen, and does not preselect one', () => {
    renderSheet();
    const approve = screen.getByRole('button', { name: /Approve/ });
    expect(approve).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /Move to another order/ }));
    expect(approve).toBeEnabled();
  });

  it('blocks reject until a reason is given', () => {
    renderSheet();
    const reject = screen.getByRole('button', { name: /Reject/ });
    expect(reject).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/Reason/), {
      target: { value: 'Container is being consolidated anyway' },
    });
    expect(reject).toBeEnabled();
  });

  it('refuses a split of the whole quantity, and accepts one strictly inside it', () => {
    renderSheet();
    fireEvent.click(screen.getByRole('button', { name: /Split the line/ }));
    const qty = screen.getByLabelText(/Quantity to move/);
    const approve = screen.getByRole('button', { name: /Approve/ });

    // Empty is not a split.
    expect(approve).toBeDisabled();
    // The whole line is a move, not a split: the remainder would be nothing (AC-D11b).
    fireEvent.change(qty, { target: { value: '240' } });
    expect(screen.getByText('Between 1 and 239.')).toBeInTheDocument();
    expect(approve).toBeDisabled();
    // Zero is nothing at all.
    fireEvent.change(qty, { target: { value: '0' } });
    expect(approve).toBeDisabled();

    fireEvent.change(qty, { target: { value: '90' } });
    expect(approve).toBeEnabled();
  });

  it('sends the chosen action and the split quantity', () => {
    const onDecide = renderSheet();
    fireEvent.click(screen.getByRole('button', { name: /Split the line/ }));
    fireEvent.change(screen.getByLabelText(/Quantity to move/), { target: { value: '90' } });
    fireEvent.click(screen.getByRole('button', { name: /Approve/ }));

    expect(onDecide).toHaveBeenCalledWith({
      exception_id: 'exc-1',
      status: 'approved',
      action_code: 'split',
      reason: null,
      split_qty: 90,
    });
  });

  it('sends the reason on reject and no action code', () => {
    const onDecide = renderSheet();
    fireEvent.change(screen.getByLabelText(/Reason/), { target: { value: 'Not worth moving' } });
    fireEvent.click(screen.getByRole('button', { name: /Reject/ }));

    expect(onDecide).toHaveBeenCalledWith({
      exception_id: 'exc-1',
      status: 'rejected',
      action_code: null,
      reason: 'Not worth moving',
      split_qty: null,
    });
  });

  it('is read-only once decided, and says who decided what', () => {
    renderSheet({
      status: 'approved',
      decided_by: 'Joey Tan',
      decided_at: '2026-08-04T18:12:00',
      decided_action: 'relink_so',
      decision_reason: 'Moved to SO26-0931',
    });
    expect(screen.getByRole('button', { name: /Approve/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Reject/ })).toBeDisabled();
    // Scoped to the decision line: "Move to another order" also labels the action card
    // above, so a bare text query matches two nodes.
    expect(screen.getByText(/Approved by Joey Tan/)).toHaveTextContent(
      'Move to another order',
    );
  });
});
