/**
 * S3-7 / S5-3: a column's finding is a Flag cell on its own row, one compact pill plus a count
 * that opens a popover with one line per finding and its actions (owner hand test on PR #1237,
 * lesson (b): no stacked cards under a row).
 */
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { blocksConfirm, buildColumnStates, columnFlag } from '../lib/scheduleTotals';
import { DeliveryScheduleFlagCell } from './DeliveryScheduleFlagCell';
import type { FlagActions } from './DeliveryScheduleFlagCell';

const phases = [{ id: 'ph1', area_group: 'TOWER', sequence: 1, label: null, delivery_date: null }];

function column(overrides: Record<string, unknown> = {}, qty = '10') {
  return buildColumnStates(
    [
      {
        product_id: 'p1',
        product_code: 'C-FH12',
        product_name: 'Floor trap',
        customer_code_raw: 'BUI-HB-C-FH12',
        reported_total: null,
        po_qty: '10',
        product_index: 0,
        ...overrides,
      },
    ],
    phases,
    [{ phase_id: 'ph1', product_id: 'p1', product_index: 0, qty }],
  )[0];
}

function actions(overrides: Partial<FlagActions> = {}): FlagActions {
  return {
    canEdit: true,
    poOptions: [],
    resolveProduct: vi.fn(),
    fixQuantities: vi.fn(),
    dismiss: vi.fn().mockResolvedValue(undefined),
    undoDismiss: vi.fn(),
    dismissing: false,
    ...overrides,
  };
}

describe('the shared blocking rule', () => {
  it('blocks exactly the columns the server refuses, and a dismissal stops it', () => {
    expect(blocksConfirm(column())).toBe(false);
    expect(blocksConfirm(column({}, '12'))).toBe(true);
    expect(blocksConfirm(column({ dismissed: true }, '12'))).toBe(false);
    // A shortfall is a warning on both sides, never a block.
    expect(blocksConfirm(column({}, '4'))).toBe(false);
    expect(columnFlag(column({}, '4'))).toBe('warning');
    expect(columnFlag(column({ dismissed: true }, '12'))).toBe('dismissed');
    expect(columnFlag(column())).toBe('agrees');
    expect(columnFlag(column({}, '12'))).toBe('blocked');
  });
});

describe('DeliveryScheduleFlagCell', () => {
  it('shows a column that agrees as the pill alone, nothing to open', () => {
    render(<DeliveryScheduleFlagCell column={column()} actions={actions()} idPrefix="t" />);
    expect(screen.getByText('Agrees')).toBeInTheDocument();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('is one pill with a count, and the sentences only in its popover', async () => {
    render(
      <DeliveryScheduleFlagCell
        column={column({ reported_total: '9' }, '12')}
        actions={actions()}
        idPrefix="t"
      />,
    );
    const trigger = screen.getByRole('button', { name: 'Blocks publish, 2 on C-FH12' });
    expect(within(trigger).getByText('2')).toBeInTheDocument();
    expect(screen.queryByTestId('flag-lines')).toBeNull();

    fireEvent.click(trigger);
    const lines = await screen.findByTestId('flag-lines');
    expect(within(lines).getAllByRole('listitem')).toHaveLength(2);
    expect(screen.getByRole('button', { name: 'Fix the quantities' })).toBeInTheDocument();
    expect(screen.getByLabelText('Change the product for BUI-HB-C-FH12')).toBeInTheDocument();
  });

  it('offers the product picker as the fix for an unidentified column', async () => {
    render(
      <DeliveryScheduleFlagCell
        column={column({ product_id: null, product_code: null, po_qty: null })}
        actions={actions()}
        idPrefix="t"
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Blocks publish/ }));
    expect(await screen.findByLabelText('Pick the product for BUI-HB-C-FH12')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Fix the quantities' })).toBeNull();
  });

  it('dismisses with a reason through the shared dialog, once', async () => {
    const dismiss = vi.fn().mockResolvedValue(undefined);
    render(
      <DeliveryScheduleFlagCell column={column({}, '12')} actions={actions({ dismiss })} idPrefix="t" />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Blocks publish/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Dismiss with a reason' }));

    const submit = screen.getByRole('button', { name: 'Dismiss 1' });
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/Reason/), { target: { value: 'Printed total is wrong' } });
    fireEvent.click(submit);
    await waitFor(() => expect(dismiss).toHaveBeenCalledTimes(1));
    expect(dismiss).toHaveBeenCalledWith(0, 'Printed total is wrong');
  });

  it('offers no action to a reader who cannot edit, only the sentences', async () => {
    render(
      <DeliveryScheduleFlagCell
        column={column({}, '12')}
        actions={actions({ canEdit: false })}
        idPrefix="t"
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Blocks publish/ }));
    await screen.findByTestId('flag-lines');
    expect(screen.queryByRole('button', { name: 'Dismiss with a reason' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Fix the quantities' })).toBeNull();
  });

  it('names a warning as needing acknowledgement and asks nothing of it', async () => {
    render(<DeliveryScheduleFlagCell column={column({}, '4')} actions={actions()} idPrefix="t" />);
    fireEvent.click(screen.getByRole('button', { name: /Needs acknowledgement, 1/ }));
    await screen.findByTestId('flag-lines');
    expect(screen.queryByRole('button', { name: 'Dismiss with a reason' })).toBeNull();
  });

  it('shows a dismissal with who and why, and puts it back on Undo', async () => {
    const undoDismiss = vi.fn();
    render(
      <DeliveryScheduleFlagCell
        column={column(
          { dismissed: true, dismissed_reason: 'Paper is wrong', dismissed_by_name: 'Aina' },
          '12',
        )}
        actions={actions({ undoDismiss })}
        idPrefix="t"
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Dismissed/ }));
    expect(await screen.findByText('Dismissed by Aina: Paper is wrong')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
    expect(undoDismiss).toHaveBeenCalledWith(0);
  });
});
