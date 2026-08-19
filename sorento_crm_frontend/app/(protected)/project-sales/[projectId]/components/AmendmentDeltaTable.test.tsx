/**
 * P11 section 9.3 - per-row accept/decline on a created amendment.
 *
 * The Decision column only appears once a row can actually be decided (`onDecide` supplied,
 * which only happens once the delta belongs to a CREATED amendment with `row_key`s) - a bare
 * preview keeps the table exactly as it always has.
 */
import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { AmendmentDeltaRow } from '../../_shared/types/projectSalesOrder.types';
import { AmendmentDeltaTable } from './AmendmentDeltaTable';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const ROWS: AmendmentDeltaRow[] = [
  {
    so_line_id: 'l3',
    row_key: 'row-1',
    line_no: 3,
    product_code: 'SRTWC8613-RL',
    description: 'ONE-PIECE WC',
    verb: 'DELAY',
    field: 'delivery_date',
    from_value: '2026-07-01',
    to_value: '2027-01-07',
    qty: '135',
    decision: 'accepted',
    declined_reason: null,
  },
  {
    so_line_id: 'l5',
    row_key: 'row-2',
    line_no: 5,
    product_code: 'SRTWCX8608-RL',
    description: 'CLOSE COUPLED PEDESTAL',
    verb: 'DELAY',
    field: 'delivery_date',
    from_value: '2026-08-03',
    to_value: '2027-01-21',
    qty: '124',
    decision: 'declined',
    declined_reason: 'Customer kept the original date for this line.',
  },
];

/** A bare preview row: nothing about decisions, exactly what `previewAmendment` returns. */
function asPreviewRow(row: AmendmentDeltaRow): AmendmentDeltaRow {
  return {
    so_line_id: row.so_line_id,
    line_no: row.line_no,
    product_code: row.product_code,
    description: row.description,
    verb: row.verb,
    field: row.field,
    from_value: row.from_value,
    to_value: row.to_value,
    qty: row.qty,
  };
}

describe('AmendmentDeltaTable', () => {
  it('carries no Decision column on a bare preview - nothing to write a decision against', () => {
    render(<AmendmentDeltaTable rows={ROWS.map(asPreviewRow)} />);

    expect(screen.queryByText('Decision')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Accept' })).toBeNull();
  });

  it('shows Accepted/Declined counts and a reason on a declined row, once decisions apply', () => {
    render(<AmendmentDeltaTable rows={ROWS} onDecide={vi.fn()} />);

    expect(screen.getByText(/Accepted 1 · Declined 1/)).toBeInTheDocument();
    const reason = screen.getByTitle('Customer kept the original date for this line.');
    expect(reason.className).toContain('truncate');
  });

  it('accepts a row with one click, calling onDecide with its row_key', () => {
    const onDecide = vi.fn();
    render(<AmendmentDeltaTable rows={ROWS} onDecide={onDecide} />);

    const rows = screen.getAllByRole('row').filter((node) => node.querySelector('td'));
    fireEvent.click(within(rows[1]).getByRole('button', { name: 'Accept' }));

    expect(onDecide).toHaveBeenCalledWith('row-2', 'accepted');
  });

  it('requires a reason before a decline is confirmed', () => {
    const onDecide = vi.fn();
    render(<AmendmentDeltaTable rows={ROWS} onDecide={onDecide} />);

    const rows = screen.getAllByRole('row').filter((node) => node.querySelector('td'));
    fireEvent.click(within(rows[0]).getByRole('button', { name: 'Decline' }));

    const confirm = within(rows[0]).getByRole('button', { name: 'Confirm decline' });
    expect(confirm).toBeDisabled();

    fireEvent.change(within(rows[0]).getByLabelText('Reason for declining line 3'), {
      target: { value: 'Pushed a second time by the same email.' },
    });
    expect(confirm).toBeEnabled();

    fireEvent.click(confirm);
    expect(onDecide).toHaveBeenCalledWith('row-1', 'declined', 'Pushed a second time by the same email.');
  });

  it('disables the decision controls once the amendment is published', () => {
    render(<AmendmentDeltaTable rows={ROWS} onDecide={vi.fn()} disabled />);

    const rows = screen.getAllByRole('row').filter((node) => node.querySelector('td'));
    expect(within(rows[0]).getByRole('button', { name: 'Accept' })).toBeDisabled();
    expect(within(rows[0]).getByRole('button', { name: 'Decline' })).toBeDisabled();
  });

  it('keys two unmatched preview rows by position, not by their shared null so_line_id', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

    const unmatchedRows: AmendmentDeltaRow[] = [
      {
        so_line_id: null,
        line_no: 7,
        product_code: 'SRTWC0001',
        description: 'FIRST UNMATCHED LINE',
        verb: 'ORDER',
        field: 'qty',
        from_value: null,
        to_value: '10',
        qty: '10',
      },
      {
        so_line_id: null,
        line_no: 8,
        product_code: 'SRTWC0002',
        description: 'SECOND UNMATCHED LINE',
        verb: 'ORDER',
        field: 'qty',
        from_value: null,
        to_value: '20',
        qty: '20',
      },
    ];

    render(<AmendmentDeltaTable rows={unmatchedRows} />);

    expect(screen.getByText('FIRST UNMATCHED LINE')).toBeInTheDocument();
    expect(screen.getByText('SECOND UNMATCHED LINE')).toBeInTheDocument();
    const keyWarning = consoleError.mock.calls.some((call) =>
      String(call[0]).includes('same key'),
    );
    expect(keyWarning).toBe(false);

    consoleError.mockRestore();
  });
});
