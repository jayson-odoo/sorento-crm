import React from 'react';
import { describe, it, expect } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import {
  ContainerRequestHistoryBars,
  ContainerRequestHistoryPeakCell,
  monthLabel,
} from './ContainerRequestHistory';
import type {
  ContainerRequestHistoryProduct,
  ContainerRequestHistorySeries,
} from '../../services/fulfilmentService';

const MONTHS = [
  '2025-08',
  '2025-09',
  '2025-10',
  '2025-11',
  '2025-12',
  '2026-01',
  '2026-02',
  '2026-03',
  '2026-04',
  '2026-05',
  '2026-06',
  '2026-07',
];

function series(peakMonth: string | null, peakQty: number): ContainerRequestHistorySeries {
  const months = MONTHS.map((month) => ({
    month,
    qty: month === peakMonth ? peakQty : 0,
  }));
  return {
    months,
    total: peakQty,
    avg: peakQty / 12,
    peak_month: peakMonth,
    peak_qty: peakQty,
  };
}

const history = (over: Partial<ContainerRequestHistoryProduct> = {}) =>
  ({
    product_id: 'p1',
    project: series('2026-04', 1240),
    retail: series('2026-06', 320),
    ...over,
  }) as ContainerRequestHistoryProduct;

describe('monthLabel', () => {
  it('reads a month as a month, never as a date', () => {
    expect(monthLabel('2026-04')).toBe('Apr 26');
    expect(monthLabel(null)).toBe('-');
  });
});

describe('ContainerRequestHistoryPeakCell', () => {
  it('names the peak month and quantity per series, and opens that series on click (AC-B6)', async () => {
    render(
      <>
        <ContainerRequestHistoryPeakCell history={history()} loading={false} kind="project" />
        <ContainerRequestHistoryPeakCell history={history()} loading={false} kind="retail" />
      </>,
    );

    const project = screen.getByTitle('Project ordered, last 12 months');
    expect(project).toHaveTextContent('1,240');
    expect(project).toHaveTextContent('Apr 26');
    const retail = screen.getByTitle('Retail ordered, last 12 months');
    expect(retail).toHaveTextContent('320');
    expect(retail).toHaveTextContent('Jun 26');

    fireEvent.click(project);
    expect(await screen.findByTestId('history-series-project')).toBeInTheDocument();
    expect(screen.queryByTestId('history-series-retail')).not.toBeInTheDocument();
  });

  it('reads a dash when the series has no orders in twelve months', () => {
    render(
      <ContainerRequestHistoryPeakCell
        history={history({ project: series(null, 0) })}
        loading={false}
        kind="project"
      />,
    );

    expect(screen.getByText('-')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('shows the sidecar is still coming rather than an empty answer', () => {
    render(<ContainerRequestHistoryPeakCell history={undefined} loading kind="project" />);

    expect(screen.getByText('Loading')).toBeInTheDocument();
  });
});

describe('ContainerRequestHistoryBars', () => {
  it('draws twelve zero-filled buckets per series, both series (AC-B7)', () => {
    render(<ContainerRequestHistoryBars history={history()} loading={false} />);

    for (const kind of ['project', 'retail']) {
      const bars = document.querySelectorAll(`[data-testid^="history-bar-${kind}-"]`);
      expect(bars).toHaveLength(12);
    }
    // Zero months are drawn, not skipped: four scattered orders must not read as a solid year.
    expect(
      document.querySelector('[data-testid="history-bar-project-2025-09"]'),
    ).toBeTruthy();
  });

  it('states each series peak, average and total under it', () => {
    render(<ContainerRequestHistoryBars history={history()} loading={false} />);

    expect(screen.getByText(/Project peak Apr 26 1,240/)).toBeInTheDocument();
    expect(screen.getByText(/Retail peak Jun 26 320/)).toBeInTheDocument();
    expect(screen.getByText(/total 1,240/)).toBeInTheDocument();
  });

  it('says a product has no orders rather than drawing twelve empty bars', () => {
    render(
      <ContainerRequestHistoryBars
        history={history({ project: series(null, 0), retail: series(null, 0) })}
        loading={false}
      />,
    );

    expect(screen.getByText('No orders in the last 12 months.')).toBeInTheDocument();
  });
});
