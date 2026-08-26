/**
 * The schedule's own cell (AC-I12): a `SupplyBar` under the quantity, and its label
 * naming what the cell still needs. Same three kinds and the same bar the list's
 * "Linked to" column draws (AC-I14), off `orderInquiryKinds`.
 */
import React from 'react';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { OrderInquiryScheduleMatrix } from './OrderInquiryScheduleMatrix';
import type {
  OrderInquiryMatrixCell,
  OrderInquiryWorklistRow,
} from '../../_shared/types/orderInquiry.types';

function worklistRow(over: Partial<OrderInquiryWorklistRow> = {}): OrderInquiryWorklistRow {
  return {
    id: 'row-1',
    qty: '10',
    state: 'raised',
    verb: 'ORDER',
    links: [],
    ...over,
  } as OrderInquiryWorklistRow;
}

function renderMatrix(rows: OrderInquiryWorklistRow[], qty: string) {
  const cell: OrderInquiryMatrixCell = { row_key: 'r', bucket_key: 'b', qty, rows };
  return render(
    <OrderInquiryScheduleMatrix
      buckets={[{ key: 'b', kind: 'dated', label: 'Jan 2026', start: '2026-01-01' }]}
      rows={[{ key: 'r', label: 'SRTWC8605-SC-RL' }]}
      rowHeader="Product"
      cells={[cell]}
      onOpenCell={vi.fn()}
    />,
  );
}

describe('OrderInquiryScheduleMatrix cell (AC-I12)', () => {
  it('draws one solid rose segment and reads "Buy N" for a cell whose rows are all unlinked', () => {
    renderMatrix([worklistRow({ qty: '85', links: [] })], '85');

    const button = screen.getByRole('button', { name: '85, 1 row, Buy 85' });
    const bar = within(button).getByTestId('supply-bar');
    // Faded: nothing in this cell is on a document yet.
    expect(bar).toHaveAttribute('data-decided', 'false');
    const segments = [...bar.querySelectorAll('span[data-kind]')];
    expect(segments).toHaveLength(1);
    expect(segments[0].getAttribute('data-kind')).toBe('buy');
  });

  it('draws sky 5 / rose 3 and reads "PO 5 · Buy 3" for a row linked 5 of 8 to a PO', () => {
    renderMatrix(
      [
        worklistRow({
          qty: '8',
          links: [{ id: 'l1', kind: 'po', document: '202601-S0044', qty: '5' }],
        }),
      ],
      '8',
    );

    const button = screen.getByRole('button', { name: '8, 1 row, PO 5 · Buy 3' });
    const bar = within(button).getByTestId('supply-bar');
    expect(bar).toHaveAttribute('data-decided', 'false');
    const kinds = [...bar.querySelectorAll('span[data-kind]')].map((el) =>
      el.getAttribute('data-kind'),
    );
    expect(kinds).toEqual(['po', 'buy']);
  });

  it('draws a solid violet segment for a row wholly linked to an SPO allocation', () => {
    renderMatrix(
      [
        worklistRow({
          qty: '10',
          links: [{ id: 'l1', kind: 'spo', document: 'SPO-2026/08-0061', qty: '10' }],
        }),
      ],
      '10',
    );

    const button = screen.getByRole('button', { name: '10, 1 row, SPO 10' });
    const bar = within(button).getByTestId('supply-bar');
    // Solid: wholly covered by a document.
    expect(bar).toHaveAttribute('data-decided', 'true');
    const segments = [...bar.querySelectorAll('span[data-kind]')];
    expect(segments).toHaveLength(1);
    expect(segments[0].getAttribute('data-kind')).toBe('spo');
  });

  it('a cancelled row contributes no bar and no supply words at all', () => {
    renderMatrix([worklistRow({ qty: '6', links: [], state: 'cancelled' })], '6');

    const button = screen.getByRole('button', { name: '6, 1 row' });
    expect(within(button).queryByTestId('supply-bar')).not.toBeInTheDocument();
  });
});
