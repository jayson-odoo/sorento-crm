/**
 * `ContainerRequestScheduleMatrix` (6b.2): the product/SO axis by day/week/month bucket, over
 * the container request's own SO lines. Each cell is its own drill trigger
 * (`SoLinesDrillPopover`) - the same component the Open SOs column drill uses - so the matrix
 * and the popover can never disagree about what a cell is made of.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import type { ContainerRequestSoLine } from '../../services/fulfilmentService';
import { buildContainerRequestMatrix } from './containerRequestMatrix';
import { ContainerRequestScheduleMatrix } from './ContainerRequestScheduleMatrix';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

function soLine(over: Partial<ContainerRequestSoLine> = {}): ContainerRequestSoLine {
  return {
    product_id: 'p1',
    item_code: 'ITEM-1',
    so_number: 'SO-1',
    customer_label: 'Acme Sdn Bhd',
    demand_class: 'project',
    order_date: '2026-08-01',
    required_date: '2026-08-19',
    qty: 10,
    ...over,
  };
}

function renderMatrix(lines: ContainerRequestSoLine[]) {
  const matrix = buildContainerRequestMatrix(lines, 'product', 'week');
  return {
    matrix,
    ...render(
      <ContainerRequestScheduleMatrix
        buckets={matrix.buckets}
        rows={matrix.rows}
        rowHeader="Product"
        cells={matrix.cells}
      />,
    ),
  };
}

describe('ContainerRequestScheduleMatrix - render', () => {
  it('renders one row per product, one column per bucket, plus a Total column', () => {
    renderMatrix([
      soLine({ item_code: 'ITEM-1', required_date: '2026-08-19' }),
      soLine({ item_code: 'ITEM-2', required_date: '2026-09-21' }),
    ]);

    expect(screen.getByText('ITEM-1')).toBeInTheDocument();
    expect(screen.getByText('ITEM-2')).toBeInTheDocument();
    const heads = screen.getAllByRole('columnheader').map((h) => h.textContent ?? '');
    expect(heads).toContain('Product');
    expect(heads).toContain('Total');
  });

  it('a filled cell shows the summed qty and the line count', () => {
    renderMatrix([
      soLine({ required_date: '2026-08-17', qty: 6 }),
      soLine({ required_date: '2026-08-19', qty: 4 }),
    ]);

    expect(screen.getAllByText('10')).toHaveLength(2); // the cell qty and the row Total
    expect(screen.getByText('2 lines')).toBeInTheDocument();
  });

  it('the row total sums every bucket for that row', () => {
    renderMatrix([
      soLine({ item_code: 'ITEM-1', required_date: '2026-08-17', qty: 6 }),
      soLine({ item_code: 'ITEM-1', required_date: '2026-09-21', qty: 4 }),
    ]);
    const row = screen.getByText('ITEM-1').closest('tr') as HTMLElement;
    expect(within(row).getByText('10')).toBeInTheDocument();
  });

  it('a bucket nobody owes for this row is a blank cell, not a rendered zero', () => {
    renderMatrix([
      soLine({ item_code: 'ITEM-1', required_date: '2026-08-17' }),
      soLine({ item_code: 'ITEM-2', required_date: '2026-09-21' }),
    ]);
    const row1 = screen.getByText('ITEM-1').closest('tr') as HTMLElement;
    // ITEM-1's row has a cell for its own bucket, and no button in the other bucket's cell.
    expect(within(row1).getAllByRole('button')).toHaveLength(1);
  });
});

describe('ContainerRequestScheduleMatrix - cell click opens the SO-lines drill popover', () => {
  it('clicking a cell opens a popover listing exactly the lines behind it', () => {
    const a = soLine({ so_number: 'SO-A', required_date: '2026-08-17', qty: 6 });
    const b = soLine({ so_number: 'SO-B', required_date: '2026-08-19', qty: 4 });
    renderMatrix([a, b]);

    fireEvent.click(screen.getByRole('button'));

    expect(screen.getByText('2 SO lines')).toBeInTheDocument();
    expect(screen.getByText('SO-A')).toBeInTheDocument();
    expect(screen.getByText('SO-B')).toBeInTheDocument();
    expect(screen.getAllByText('Acme Sdn Bhd')).toHaveLength(2);
  });

  it('the popover title names the row and bucket the cell belongs to', () => {
    const a = soLine({ item_code: 'ITEM-1', required_date: '2026-08-19' });
    renderMatrix([a]);

    fireEvent.click(screen.getByRole('button'));

    expect(screen.getByText(/ITEM-1 - 17 Aug 2026/)).toBeInTheDocument();
  });

  it('an empty request (no lines at all) renders no rows and no clickable cells', () => {
    renderMatrix([]);
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    expect(screen.queryAllByRole('row')).toHaveLength(1); // header row only
  });
});
