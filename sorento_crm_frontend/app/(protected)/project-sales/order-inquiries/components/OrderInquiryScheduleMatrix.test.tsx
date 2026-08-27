/**
 * The schedule's own cell (AC-I12): a `SupplyBar` under the quantity, and its label
 * naming what the cell still needs. Same three kinds and the same bar the list's
 * "Linked to" column draws (AC-I14), off `orderInquiryKinds`.
 */
import React from 'react';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { OrderInquiryScheduleMatrix } from './OrderInquiryScheduleMatrix';
import { buildOrderInquiryMatrix } from '../../_shared/lib/orderInquiryMatrix';
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

/** The whole way through: rows in, matrix built, matrix rendered - which is what pins
 *  the headline figure and the bar under it to the SAME arithmetic. */
function renderBuilt(rows: OrderInquiryWorklistRow[]) {
  const matrix = buildOrderInquiryMatrix(rows, 'product', 'month');
  return render(
    <OrderInquiryScheduleMatrix
      buckets={matrix.buckets}
      rows={matrix.rows}
      rowHeader="Product"
      cells={matrix.cells}
      onOpenCell={vi.fn()}
    />,
  );
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

    const button = screen.getByRole('button', { name: '85 owed, 1 row, Buy 85' });
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

    const button = screen.getByRole('button', { name: '8 owed, 1 row, PO 5 · Buy 3' });
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

    const button = screen.getByRole('button', { name: '10 owed, 1 row, SPO 10' });
    const bar = within(button).getByTestId('supply-bar');
    // Solid: wholly covered by a document.
    expect(bar).toHaveAttribute('data-decided', 'true');
    const segments = [...bar.querySelectorAll('span[data-kind]')];
    expect(segments).toHaveLength(1);
    expect(segments[0].getAttribute('data-kind')).toBe('spo');
  });

  it('a cancelled row contributes no bar and no supply words at all', () => {
    renderBuilt([worklistRow({ qty: '6', links: [], state: 'cancelled' })]);

    // Nothing is owed here any more, so the cell says nothing is.
    const button = screen.getByRole('button', { name: '0 owed, 1 row' });
    expect(within(button).queryByTestId('supply-bar')).not.toBeInTheDocument();
  });

  it('the headline counts only what is still owed, so it cannot outrun its own bar', () => {
    // The reported defect: 91 over a bar reading "Buy 85", because the cancelled six were
    // in the headline and in nothing else.
    renderBuilt([
      worklistRow({ id: 'live', qty: '85', links: [] }),
      worklistRow({ id: 'called-off', qty: '6', links: [], state: 'cancelled' }),
    ]);

    const button = screen.getByRole('button', { name: '85 owed, 2 rows, Buy 85' });
    const bar = within(button).getByTestId('supply-bar');
    const segments = [...bar.querySelectorAll('span[data-kind]')].map((el) => ({
      kind: el.getAttribute('data-kind'),
      qty: el.getAttribute('data-qty'),
    }));
    expect(segments).toEqual([{ kind: 'buy', qty: '85' }]);
    // The cancelled row is still IN the cell - its name says "2 rows" - because the
    // drilldown is where a person goes to see what happened to it.
  });
});
