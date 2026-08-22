/**
 * The three-way `Confirm as proposed` / `Amend` / `Leave on the board` control
 * (`PLAN-so-book-diff-replanning.md`, the captain 19 August 2026: "clicking accept here has
 * no effect" - a `replan` row's old `accept` recorded a decision Apply never executed).
 *
 * `BoardAmendDialog` is heavy (it composes against `lineBalance`/`lineBlockers` and mounts
 * `BorrowAddDialog`), so it is mocked to a thin stub that only proves the wiring: the right
 * `contribution` reaches it, and its `onSave` produces a real `ConfirmLine` via the SAME
 * `confirmLinesFor` the board's own Confirm posts (not mocked - that IS the thing being
 * proven, that Amend here writes what accepting it on the board would have).
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { BoardContribution, BoardDecision } from '../../_shared/types/fulfilmentPlanning.types';
import type { PlanningChangeRow } from '../../_shared/types/planningChange.types';

const toastError = vi.fn();
vi.mock('sonner', () => ({ toast: { error: (...args: unknown[]) => toastError(...args) } }));

let savedDecision: BoardDecision | null = null;
vi.mock('../../fulfilment-planning/components/BoardAmendDialog', () => ({
  BoardAmendDialog: ({
    contribution,
    onSave,
    onCancel,
  }: {
    contribution: BoardContribution;
    onSave: (decision: BoardDecision) => void;
    onCancel: () => void;
  }) => (
    <div data-testid="amend-dialog-stub">
      <span data-testid="amend-dialog-line">{contribution.line_no}</span>
      <button
        type="button"
        onClick={() => onSave(savedDecision as BoardDecision)}
      >
        Save the amendment
      </button>
      <button type="button" onClick={onCancel}>
        Cancel
      </button>
    </div>
  ),
}));

import { PlanningChangeDecisionControl } from './PlanningChangeDecisionControl';

const PROPOSAL: BoardContribution = {
  key: 'pcb-1-so400875-l2',
  sales_order_id: 'so-400875',
  so_number: 'SO400875',
  line_no: 2,
  item_code: 'CB231SS-NL',
  qty: '60',
  qty_outstanding: '60',
  fulfilment_location: 'BRW-BB',
  fulfilment_warehouse_id: 'wh-brw-bb',
  project_line_id: 'line-2',
  unplannable: false,
  rank_score: 0,
  rank_factors: [],
  contested: false,
  covered: false,
  sources: [
    {
      kind: 'reserve',
      qty: '40',
      location: 'BRW-BB',
      warehouse_id: 'wh-brw-bb',
      reason: 'Free stock at BRW-BB covers this much.',
    },
    { kind: 'buy', qty: '20', location: null, reason: 'The residual is bought.' },
  ],
};

function baseRow(overrides: Partial<PlanningChangeRow> = {}): PlanningChangeRow {
  return {
    id: 'pcr-7',
    line_no: 2,
    item_code: 'CB231SS-NL',
    kind: 'advanced',
    from: { required_date: '2027-02-18', qty: '60', status: 'open' },
    to: { required_date: '2027-02-04', qty: '60', status: 'open' },
    days_moved: -14,
    held: null,
    facts: {
      dealer_hot_selling: { value: false, where: [] },
      project_hot_selling: { value: false, where: [] },
      discontinued: false,
      days_moved: -14,
      within_reserve_window: {
        value: true, window_days: 60, new_date: '2027-02-04', window_end: '2027-04-19',
      },
      buy_actioned: { value: false, po_number: null },
    },
    suggested: 'replan',
    why: 'Advanced 14 days; the line runs the ladder again at the new date now.',
    proposal: PROPOSAL,
    inquiry_rows: [],
    decision: null,
    applied_state: 'pending',
    board_link: '/project-sales/fulfilment-planning?orders=SO400875&cell=CB231SS-NL|2027-02-04',
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  savedDecision = null;
});

describe('PlanningChangeDecisionControl - a row carrying a proposal', () => {
  it('offers Confirm as proposed / Amend / Leave on the board, not Accept/Keep as is', () => {
    render(
      <PlanningChangeDecisionControl row={baseRow()} onChange={vi.fn()} boardHref="/board" />,
    );

    expect(screen.getByRole('button', { name: 'Confirm as proposed' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Amend' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Leave on the board' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Accept' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Keep as is' })).not.toBeInTheDocument();
  });

  it('Confirm as proposed calls onChange with no composition - the server derives it', () => {
    const onChange = vi.fn();
    render(<PlanningChangeDecisionControl row={baseRow()} onChange={onChange} boardHref="/board" />);

    fireEvent.click(screen.getByRole('button', { name: 'Confirm as proposed' }));

    expect(onChange).toHaveBeenCalledWith('confirm');
  });

  it('Leave on the board calls onChange(null)', () => {
    const onChange = vi.fn();
    render(
      <PlanningChangeDecisionControl
        row={baseRow({ decision: 'confirm' })}
        onChange={onChange}
        boardHref="/board"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Leave on the board' }));

    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('Amend opens the board editor over the row\'s own proposal', () => {
    render(
      <PlanningChangeDecisionControl row={baseRow()} onChange={vi.fn()} boardHref="/board" />,
    );

    expect(screen.queryByTestId('amend-dialog-stub')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Amend' }));

    expect(screen.getByTestId('amend-dialog-stub')).toBeInTheDocument();
    expect(screen.getByTestId('amend-dialog-line')).toHaveTextContent('2');
  });

  it("the editor's Save composes a real ConfirmLine and calls onChange('amend', composed)", () => {
    savedDecision = {
      verdict: 'amended',
      reserve: [{ warehouse_id: 'wh-brw-bb', location: 'BRW-BB', qty: '40' }],
      borrow: [],
      timely_spo_qty: '0',
      buy_qty: '20',
      reason: 'Own location has stock the proposal did not use.',
    };
    const onChange = vi.fn();
    render(<PlanningChangeDecisionControl row={baseRow()} onChange={onChange} boardHref="/board" />);

    fireEvent.click(screen.getByRole('button', { name: 'Amend' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save the amendment' }));

    expect(onChange).toHaveBeenCalledWith(
      'amend',
      expect.objectContaining({
        project_line_id: 'line-2',
        reserve: [{ warehouse_id: 'wh-brw-bb', qty: '40' }],
        buy_qty: '20',
        amend_reason: 'Own location has stock the proposal did not use.',
      }),
    );
    // The dialog closes once the composition is handed off.
    expect(screen.queryByTestId('amend-dialog-stub')).not.toBeInTheDocument();
  });

  it('a composition the board could not post (no reserve warehouse addressable) toasts and does not write', () => {
    savedDecision = {
      verdict: 'amended',
      reserve: [],
      borrow: [],
      timely_spo_qty: '0',
      buy_qty: '0',
      reason: undefined,
    };
    const onChange = vi.fn();
    // No project_line_id -> `lineFor` refuses to compose (`no_mirror`).
    const row = baseRow({ proposal: { ...PROPOSAL, project_line_id: null } });
    render(<PlanningChangeDecisionControl row={row} onChange={onChange} boardHref="/board" />);

    fireEvent.click(screen.getByRole('button', { name: 'Amend' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save the amendment' }));

    expect(onChange).not.toHaveBeenCalled();
    expect(toastError).toHaveBeenCalled();
  });

  it('shows the stored composition once amended, with an Edit link back to the dialog', () => {
    const row = baseRow({
      decision: 'amend',
      composition: {
        project_line_id: 'line-2',
        timely_spo_qty: '0',
        reserve: [{ warehouse_id: 'wh-brw-bb', qty: '40' }],
        borrow: [],
        buy_qty: '20',
      },
    });
    render(<PlanningChangeDecisionControl row={row} onChange={vi.fn()} boardHref="/board" />);

    expect(screen.getByText(/Amended: Reserve 40 at BRW-BB · Buy 20/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Edit/ })).toBeInTheDocument();
  });
});

describe('PlanningChangeDecisionControl - outcome states are unaffected by a proposal', () => {
  it('still shows Applied/Failed/Superseded regardless of a proposal being present', () => {
    const { rerender } = render(
      <PlanningChangeDecisionControl
        row={baseRow({ applied_state: 'applied' })}
        onChange={vi.fn()}
        boardHref="/board"
      />,
    );
    expect(screen.getByText('Applied')).toBeInTheDocument();

    rerender(
      <PlanningChangeDecisionControl
        row={baseRow({ applied_state: 'failed', applied_reason: 'stale reserve' })}
        onChange={vi.fn()}
        boardHref="/board"
      />,
    );
    expect(screen.getByText('Failed')).toBeInTheDocument();

    rerender(
      <PlanningChangeDecisionControl
        row={baseRow({ applied_state: 'superseded' })}
        onChange={vi.fn()}
        boardHref="/board"
      />,
    );
    expect(screen.getByText('Superseded on the board')).toBeInTheDocument();
  });
});
