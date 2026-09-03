/**
 * S4 (`PLAN-scm-spo-planner-feedback-3sep.md`) - the schedule cell is a plain `button` now
 * (no hover `Popover`), tinted by what it holds, and the legend under the matrix names the
 * two colours (AC-D1, AC-D5).
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

import { SpoScheduleMatrixTable } from './SpoScheduleMatrixTable';
import { buildSpoScheduleMatrix, type SpoMatrixEntry } from './spoScheduleMatrix';

function entry(over: Partial<SpoMatrixEntry<{ id: string }>> = {}): SpoMatrixEntry<{ id: string }> {
  return {
    row_key: 'item:ABC',
    row_label: 'ABC',
    row_description: null,
    shipment_line_id: 'sl-1',
    date: '2026-09-01',
    qty: 10,
    detail: { id: 'e1' },
    ...over,
  };
}

describe('SpoScheduleMatrixTable - cell tint (AC-D1, AC-E8)', () => {
  it('a cell holding this SPO\'s take is tinted bg-primary/10 with the figure bold', () => {
    const matrix = buildSpoScheduleMatrix([entry()]);
    render(
      <SpoScheduleMatrixTable
        rowHeader="Product"
        rows={matrix.rows}
        buckets={matrix.buckets}
        cells={matrix.cells}
        onCellClick={() => {}}
      />,
    );

    const button = screen.getByRole('button', { name: /ABC/ });
    expect(button.className).toContain('bg-primary/10');
    expect(within(button).getByText('10').className).toContain('font-semibold');
  });

  it('an empty cell has no tint - nothing renders in it at all', () => {
    const matrix = buildSpoScheduleMatrix([entry()]);
    const { container } = render(
      <SpoScheduleMatrixTable
        rowHeader="Product"
        rows={matrix.rows}
        buckets={[{ key: 'no_date', kind: 'no_date', label: 'No date' }, ...matrix.buckets]}
        cells={matrix.cells}
        onCellClick={() => {}}
      />,
    );

    const emptyCell = container.querySelector('[data-cell="item:ABC|no_date"]') as HTMLElement;
    expect(emptyCell.querySelector('button')).toBeNull();
    expect(emptyCell.className).not.toContain('bg-primary/10');
  });

  it('a cell whose only quantity is taken renders bg-muted / text-muted-foreground (AC-E8)', () => {
    const matrix = buildSpoScheduleMatrix([entry({ qty: 0, taken_qty: 15 })]);
    render(
      <SpoScheduleMatrixTable
        rowHeader="Product"
        rows={matrix.rows}
        buckets={matrix.buckets}
        cells={matrix.cells}
        onCellClick={() => {}}
      />,
    );

    const button = screen.getByRole('button', { name: /ABC/ });
    expect(button.className).toContain('bg-muted');
    expect(button.className).toContain('text-muted-foreground');
    expect(button.className).not.toContain('bg-primary/10');
    expect(screen.getByText('15')).toBeTruthy();
  });

  it('a mixed cell shows the tinted figure and a muted "+N other SPO" line (AC-E8)', () => {
    const matrix = buildSpoScheduleMatrix([entry({ qty: 10, taken_qty: 5 })]);
    render(
      <SpoScheduleMatrixTable
        rowHeader="Product"
        rows={matrix.rows}
        buckets={matrix.buckets}
        cells={matrix.cells}
        onCellClick={() => {}}
      />,
    );

    const button = screen.getByRole('button', { name: /ABC/ });
    expect(button.className).toContain('bg-primary/10');
    expect(within(button).getByText('10').className).toContain('font-semibold');
    expect(within(button).getByText('+5 other SPO')).toBeTruthy();
    expect(within(button).queryByText(/line/)).toBeNull();
  });

  it('a mixed cell names the SPO once `taken_by` carries one - "+N on SPO-..." (S5)', () => {
    const matrix = buildSpoScheduleMatrix([
      entry({ qty: 10, taken_qty: 5, taken_by: ['CRM-SPO-2026/09-0001'] }),
    ]);
    render(
      <SpoScheduleMatrixTable
        rowHeader="Product"
        rows={matrix.rows}
        buckets={matrix.buckets}
        cells={matrix.cells}
        onCellClick={() => {}}
      />,
    );

    const button = screen.getByRole('button', { name: /ABC/ });
    expect(within(button).getByText('+5 on CRM-SPO-2026/09-0001')).toBeTruthy();
  });

  it('a mixed cell names the FIRST SPO when several entries carry different ones (S5)', () => {
    const matrix = buildSpoScheduleMatrix([
      entry({ qty: 10, taken_qty: 3, taken_by: ['CRM-SPO-2026/09-0001'] }),
      entry({ qty: 0, taken_qty: 2, taken_by: ['CRM-SPO-2026/09-0002'] }),
    ]);
    render(
      <SpoScheduleMatrixTable
        rowHeader="Product"
        rows={matrix.rows}
        buckets={matrix.buckets}
        cells={matrix.cells}
        onCellClick={() => {}}
      />,
    );

    const button = screen.getByRole('button', { name: /ABC/ });
    expect(within(button).getByText('+5 on CRM-SPO-2026/09-0001')).toBeTruthy();
    expect(within(button).queryByText(/0002/)).toBeNull();
  });

  it('an ordinary cell keeps the "N line(s)" second line', () => {
    const matrix = buildSpoScheduleMatrix([
      entry({ shipment_line_id: 'sl-1', detail: { id: 'e1' } }),
      entry({ shipment_line_id: 'sl-1', detail: { id: 'e2' } }),
    ]);
    render(
      <SpoScheduleMatrixTable
        rowHeader="Product"
        rows={matrix.rows}
        buckets={matrix.buckets}
        cells={matrix.cells}
        onCellClick={() => {}}
      />,
    );

    expect(screen.getByText('2 lines')).toBeTruthy();
  });
});

describe('SpoScheduleMatrixTable - click opens the lightbox, no popover (AC-D2)', () => {
  it('clicking a cell calls onCellClick with that cell and its bucket', () => {
    const matrix = buildSpoScheduleMatrix([entry()]);
    const onCellClick = vi.fn();
    render(
      <SpoScheduleMatrixTable
        rowHeader="Product"
        rows={matrix.rows}
        buckets={matrix.buckets}
        cells={matrix.cells}
        onCellClick={onCellClick}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /ABC/ }));

    expect(onCellClick).toHaveBeenCalledTimes(1);
    const [cell, bucket] = onCellClick.mock.calls[0];
    expect(cell.row_key).toBe('item:ABC');
    expect(bucket.key).toBe(matrix.buckets[0].key);
  });

  it('renders no popover content anywhere in the table', () => {
    const matrix = buildSpoScheduleMatrix([entry()]);
    const { container } = render(
      <SpoScheduleMatrixTable
        rowHeader="Product"
        rows={matrix.rows}
        buckets={matrix.buckets}
        cells={matrix.cells}
        onCellClick={() => {}}
      />,
    );

    expect(container.querySelector('[data-radix-popper-content-wrapper]')).toBeNull();
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});

describe('SpoScheduleMatrixTable - legend (AC-D5)', () => {
  it('renders a legend under the matrix with both swatches labelled', () => {
    const matrix = buildSpoScheduleMatrix([entry()]);
    render(
      <SpoScheduleMatrixTable
        rowHeader="Product"
        rows={matrix.rows}
        buckets={matrix.buckets}
        cells={matrix.cells}
        onCellClick={() => {}}
      />,
    );

    const legend = screen.getByTestId('spo-schedule-legend');
    expect(legend.textContent).toContain('This SPO');
    expect(legend.textContent).toContain('Another SPO');
  });
});
