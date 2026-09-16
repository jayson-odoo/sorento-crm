/**
 * The schedule's own cell (AC-X1/AC-X4, S3 - PLAN-scm-oi-worklist-excel-parity.md).
 *
 * Rewritten for the SERVER cell contract: `{ axis_key, axis_label, period, qty, buy,
 * po, spo, rows }`, `rows` a COUNT (never the rows themselves - S3, "the drilldown
 * keeps calling the list"). The old shape this replaces (`buildOrderInquiryMatrix(rows,
 * axis, by)` grouping raw worklist rows client-side into `{ row_key, bucket_key, qty,
 * rows: WorklistRow[] }`) is what the client-side matrix WAS before S3 moved the GROUP
 * BY server-side; the new `buildOrderInquiryMatrix(cells, granularity)` only ever
 * builds display headers off cells the server already computed.
 */
import React from 'react';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { OrderInquiryScheduleMatrix } from './OrderInquiryScheduleMatrix';
import { buildOrderInquiryMatrix } from '../../_shared/lib/orderInquiryMatrix';
import type { OrderInquiryMatrixCell } from '../../_shared/types/orderInquiry.types';

function cell(over: Partial<OrderInquiryMatrixCell> = {}): OrderInquiryMatrixCell {
  return {
    axis_key: 'product-1',
    axis_label: 'SRTWC8605-SC-RL',
    period: '2026-01-01',
    qty: '0',
    buy: '0',
    po: '0',
    spo: '0',
    rows: 1,
    ...over,
  };
}

/** The whole way through: server cells in, headers built, matrix rendered - which is
 * what pins the headline figure and the bar under it to the SAME server arithmetic. */
function renderBuilt(cells: OrderInquiryMatrixCell[]) {
  const matrix = buildOrderInquiryMatrix(cells, 'month');
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

describe('OrderInquiryScheduleMatrix cell, server contract (AC-X1, AC-X4)', () => {
  it('draws one solid rose segment and reads "Buy N" for a cell that is all Buy', () => {
    renderBuilt([cell({ qty: '85', buy: '85', po: '0', spo: '0', rows: 1 })]);

    const button = screen.getByRole('button', { name: '85 owed, 1 row, Buy 85' });
    const bar = within(button).getByTestId('supply-bar');
    // Faded: nothing in this cell is on a document yet.
    expect(bar).toHaveAttribute('data-decided', 'false');
    const segments = [...bar.querySelectorAll('span[data-kind]')];
    expect(segments).toHaveLength(1);
    expect(segments[0].getAttribute('data-kind')).toBe('buy');
  });

  it('draws rose 3 / sky 5 and reads "Buy 3 · Purchased 5" off the server stage sums, in stage order', () => {
    renderBuilt([cell({ qty: '8', buy: '3', po: '5', spo: '0', rows: 1 })]);

    const button = screen.getByRole('button', {
      name: '8 owed, 1 row, Buy 3 · Purchased 5',
    });
    const bar = within(button).getByTestId('supply-bar');
    expect(bar).toHaveAttribute('data-decided', 'false');
    const kinds = [...bar.querySelectorAll('span[data-kind]')].map((el) =>
      el.getAttribute('data-kind'),
    );
    expect(kinds).toEqual(['buy', 'po']);
  });

  it('draws a solid violet segment for a cell wholly on SPO allocations (incoming)', () => {
    renderBuilt([cell({ qty: '10', buy: '0', po: '0', spo: '10', rows: 1 })]);

    const button = screen.getByRole('button', { name: '10 owed, 1 row, Incoming 10' });
    const bar = within(button).getByTestId('supply-bar');
    // Solid: wholly covered by a document, per the server's `buy` sum of zero.
    expect(bar).toHaveAttribute('data-decided', 'true');
    const segments = [...bar.querySelectorAll('span[data-kind]')];
    expect(segments).toHaveLength(1);
    expect(segments[0].getAttribute('data-kind')).toBe('spo');
  });

  it('a cell with nothing owed and no stage sums draws no bar, just the row count', () => {
    renderBuilt([cell({ qty: '0', buy: '0', po: '0', spo: '0', rows: 1 })]);

    const button = screen.getByRole('button', { name: '0 owed, 1 row' });
    expect(within(button).queryByTestId('supply-bar')).not.toBeInTheDocument();
  });

  it('the headline and the bar both read off the same server totals for a multi-row cell', () => {
    renderBuilt([cell({ qty: '85', buy: '85', po: '0', spo: '0', rows: 2 })]);

    const button = screen.getByRole('button', { name: '85 owed, 2 rows, Buy 85' });
    const bar = within(button).getByTestId('supply-bar');
    const segments = [...bar.querySelectorAll('span[data-kind]')].map((el) => ({
      kind: el.getAttribute('data-kind'),
      qty: el.getAttribute('data-qty'),
    }));
    expect(segments).toEqual([{ kind: 'buy', qty: '85' }]);
  });

  it('builds one row per distinct axis_key/axis_label and one bucket per distinct period', () => {
    renderBuilt([
      cell({ axis_key: 'p1', axis_label: 'Product One', period: '2026-01-01', qty: '5', buy: '5' }),
      cell({ axis_key: 'p1', axis_label: 'Product One', period: '2026-02-01', qty: '3', buy: '3' }),
      cell({ axis_key: 'p2', axis_label: 'Product Two', period: '2026-01-01', qty: '7', buy: '7' }),
    ]);

    expect(screen.getByText('Product One')).toBeInTheDocument();
    expect(screen.getByText('Product Two')).toBeInTheDocument();
    // Two distinct periods -> two bucket columns, "Jan 2026" and "Feb 2026" at month
    // granularity - the label is derived client-side off the ISO `period`, never sent.
    expect(screen.getByText('Jan 2026')).toBeInTheDocument();
    expect(screen.getByText('Feb 2026')).toBeInTheDocument();
  });
});
