/**
 * The breakdown behind one cell (PLAN section 13, journey step 4).
 *
 * The columns are the captain's own list, so they are asserted by name: which sales order,
 * which customer, which project, the quantity, and where it is sourced from. Each row also owes
 * the balance line the per-line card owes ("23 open = ... + 23 buy"), because a row that states
 * a Buy without saying what it is instead of is not an explanation.
 *
 * The verbs write into the DRAFT and nothing else. Nothing in this dialog claims a cell
 * committed anything: the commit is the per-order confirmation on the rail behind it (13.4).
 */
import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { BoardCellBreakdownDialog } from './BoardCellBreakdownDialog';
import { buildBoard, type BoardDemandLine } from '../../_shared/lib/fulfilmentBoard';
import type { BoardDraft } from '../../_shared/types/fulfilmentPlanning.types';

const TODAY = '2026-08-18';

function demand(overrides: Partial<BoardDemandLine> = {}): BoardDemandLine {
  return {
    sales_order_id: 'so-a',
    so_number: 'SO403340',
    customer_name: 'SETIA-WOOD INDUSTRIES SDN BHD (PROJECT)',
    project_label: 'SETIA-WOOD INDUSTRIES/100U DSTH (DIMINA) @ SETIA',
    line_no: 1,
    item_code: 'WESERP10B',
    qty: '100',
    required_date: '2026-09-04',
    fulfilment_location: 'BRW-BB',
    priority: null,
    ...overrides,
  };
}

function cellOf(lines: BoardDemandLine[], freeStock: Record<string, string> = {}) {
  return buildBoard(lines, { today: TODAY, freeStock }).cells[0];
}

function renderDialog(
  lines: BoardDemandLine[],
  freeStock: Record<string, string> = {},
  draft: BoardDraft = {},
) {
  const onDecide = vi.fn();
  render(
    <BoardCellBreakdownDialog
      cell={cellOf(lines, freeStock)}
      bucketLabel="w/c 31 Aug 2026"
      draft={draft}
      onDecide={onDecide}
      onClose={vi.fn()}
    />,
  );
  return { onDecide };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('BoardCellBreakdownDialog: what a row states', () => {
  it('names the cell and how much of it is decided', () => {
    renderDialog([demand()]);
    expect(screen.getByText('WESERP10B · w/c 31 Aug 2026')).toBeInTheDocument();
    expect(screen.getByText('100 across 1 line, 0 decided')).toBeInTheDocument();
  });

  it('carries the sales order, customer, project and quantity the captain asked for', () => {
    renderDialog([demand()]);
    expect(screen.getByText(/SO403340/)).toBeInTheDocument();
    expect(
      screen.getByText('SETIA-WOOD INDUSTRIES SDN BHD (PROJECT)'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('SETIA-WOOD INDUSTRIES/100U DSTH (DIMINA) @ SETIA'),
    ).toBeInTheDocument();
    // The quantity, beside the word that says what it is. Asserted as the pair because the
    // bare number also appears in the balance line below it.
    const owed = screen.getByText('owed').closest('div');
    expect(owed?.textContent).toBe('100 owed');
  });

  it('carries the location per row, because that is where it is a fact (13.7)', () => {
    renderDialog([
      demand({ line_no: 1, qty: '22', fulfilment_location: 'BRW-BB' }),
      demand({ line_no: 2, qty: '21', fulfilment_location: 'BRW' }),
    ]);
    // Once per row, and once each in the strip at the top of the dialog.
    expect(screen.getAllByText('BRW-BB').length).toBeGreaterThan(0);
    expect(screen.getAllByText('BRW').length).toBeGreaterThan(0);
    expect(screen.getByText('BRW-BB · 22')).toBeInTheDocument();
    expect(screen.getByText('BRW · 21')).toBeInTheDocument();
  });

  it('shows where the quantity is sourced from, with the reason the rule wrote', () => {
    renderDialog([demand({ qty: '100' })], { 'WESERP10B|BRW-BB': '40' });
    expect(screen.getByText(/Reserve/)).toBeInTheDocument();
    expect(screen.getByText(/Buy/)).toBeInTheDocument();
    expect(
      screen.getByText('Free unclaimed stock at BRW-BB covers this much by the required date.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Free stock at BRW-BB ran out on this line; the residual is bought.'),
    ).toBeInTheDocument();
  });

  it('owes the same balance line the per-line card owes', () => {
    renderDialog([demand({ qty: '100' })], { 'WESERP10B|BRW-BB': '40' });
    expect(screen.getByText('100 owed = 40 reserve + 0 incoming + 60 buy')).toBeInTheDocument();
  });

  it('says when the stock was already committed to earlier demand (13.5)', () => {
    renderDialog(
      [
        demand({ sales_order_id: 'so-a', so_number: 'SO403340', line_no: 1, qty: '100', required_date: '2026-09-04' }),
        demand({ sales_order_id: 'so-b', so_number: 'SO398322', line_no: 2, qty: '100', required_date: '2026-09-02' }),
      ],
      { 'WESERP10B|BRW-BB': '100' },
    );
    expect(
      screen.getByText(
        'Free stock at this location was already committed to earlier demand, so this line is bought.',
      ),
    ).toBeInTheDocument();
  });

  it('lists the rows in the order the allocation rule served them', () => {
    renderDialog([
      demand({ sales_order_id: 'so-a', so_number: 'SO403340', line_no: 1, required_date: '2026-09-04' }),
      demand({ sales_order_id: 'so-b', so_number: 'SO398322', line_no: 2, required_date: '2026-09-02' }),
    ]);
    const rendered = screen
      .getAllByTitle(/^SO\d+$/)
      .map((node) => node.textContent?.replace(/\s+/g, ' ').trim());
    expect(rendered[0]).toContain('SO398322');
    expect(rendered[1]).toContain('SO403340');
  });
});

describe('BoardCellBreakdownDialog: approve, amend, reject', () => {
  it('approves a row', () => {
    const { onDecide } = renderDialog([demand()]);
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    expect(onDecide).toHaveBeenCalledWith(expect.any(String), { verdict: 'approved' });
  });

  it('rejects a row, and a rejection carries a reason', () => {
    const { onDecide } = renderDialog([demand()]);
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }));
    expect(onDecide).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ verdict: 'rejected', reason: expect.any(String) }),
    );
  });

  it('takes an amendment at the proposed quantity without demanding a reason', () => {
    const { onDecide } = renderDialog([demand({ qty: '100' })], { 'WESERP10B|BRW-BB': '40' });
    fireEvent.click(screen.getByRole('button', { name: 'Amend' }));
    expect(screen.queryByLabelText(/Reason/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Save the amendment' }));
    expect(onDecide).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ verdict: 'amended', reserve_qty: '40' }),
    );
  });

  it('demands a reason the moment the amendment displaces the rule, and blocks Save until it has one', () => {
    const { onDecide } = renderDialog([demand({ qty: '100' })], { 'WESERP10B|BRW-BB': '40' });
    fireEvent.click(screen.getByRole('button', { name: 'Amend' }));

    fireEvent.change(screen.getByRole('spinbutton', { name: /Reserve for SO403340 line 1/ }), {
      target: { value: '10' },
    });

    const save = screen.getByRole('button', { name: 'Save the amendment' });
    expect(save).toBeDisabled();

    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'Holding the rest for the Nadi 3 handover.' },
    });
    expect(save).toBeEnabled();

    fireEvent.click(save);
    expect(onDecide).toHaveBeenCalledWith(expect.any(String), {
      verdict: 'amended',
      reserve_qty: '10',
      reason: 'Holding the rest for the Nadi 3 handover.',
    });
  });

  it('shows a decided row as decided, and lets it be undone', () => {
    const cell = cellOf([demand()]);
    const key = cell.contributions[0].key;
    const { onDecide } = renderDialog([demand()], {}, { [key]: { verdict: 'approved' } });

    expect(screen.getByText('Approved')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
    expect(onDecide).toHaveBeenCalledWith(key, null);
  });

  it('states an amended row at the quantity it was amended to', () => {
    const cell = cellOf([demand()]);
    const key = cell.contributions[0].key;
    renderDialog([demand()], {}, { [key]: { verdict: 'amended', reserve_qty: '10', reason: 'Held back.' } });
    expect(screen.getByText('Amended to reserve 10')).toBeInTheDocument();
    expect(screen.getByText('Held back.')).toBeInTheDocument();
  });
});

describe('BoardCellBreakdownDialog: a line with no location (AC-FP16)', () => {
  it('offers no verdict at all, and says why', () => {
    renderDialog([demand({ fulfilment_location: null })]);

    expect(
      screen.getByText(
        'This line cannot be decided here: its sales order states no fulfilment location.',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Amend' })).not.toBeInTheDocument();
  });

  it('still shows its quantity, so the demand is not hidden from the reader', () => {
    renderDialog([demand({ qty: '24', fulfilment_location: null })]);
    const dialog = screen.getByRole('dialog');
    const owed = within(dialog).getByText('owed').closest('div');
    expect(owed?.textContent).toBe('24 owed');
    expect(within(dialog).getByText('No location · 24')).toBeInTheDocument();
  });
});
