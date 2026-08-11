/**
 * The third suggestion on a row (S13f): the AutoCount level to set.
 *
 * The one rule: it is an ASK. The engine never changes a level, so the cell must read as
 * "set it to 24" with the arithmetic behind it - never as something already done.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PlanLevelCell } from './PlanLevelCell';
import type { LevelSuggestion } from '../lib/levelSuggestion';

class ResizeObserverStub { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);

// The month bars render through react-apexcharts, which needs a real layout engine. The
// assertions here are about WHICH months and quantities feed the chart, not about SVG.
vi.mock('react-apexcharts', () => ({
  default: ({ options, series }: {
    options: { xaxis?: { categories?: string[] } };
    series: { data: number[] }[];
  }) => (
    <div data-testid="level-chart">
      {(options.xaxis?.categories ?? []).join(' ')} | {series[0]?.data.join(' ')}
    </div>
  ),
}));

const suggestion = (over: Partial<LevelSuggestion> = {}): LevelSuggestion => ({
  product_id: 'p1',
  warehouse_id: 'w1',
  product_code: 'SRT-100',
  product_name: 'Basin',
  warehouse_code: 'BRW',
  warehouse_name: 'Branch West',
  current_level: 20,
  current_source: 'autocount',
  suggested_level: 24,
  suggested_at: '2026-08-10T00:00:00',
  amended_level: null,
  amended_at: null,
  suggested_quantity: null,
  master_reorder_quantity: null,
  basis: {
    months: [
      { month: '2026-05', qty: 12 },
      { month: '2026-06', qty: 12 },
      { month: '2026-07', qty: 12 },
    ],
    months_studied: 3,
    total_qty: 36,
    avg_monthly: 12,
    cover_months: 2,
    raw_level: 24,
    moq: null,
    order_multiple: null,
    trend: 'rising',
    no_movement: false,
  },
  ...over,
});

describe('PlanLevelCell', () => {
  it('asks for the change with both numbers on the row', () => {
    render(<PlanLevelCell suggestion={suggestion()} />);

    expect(screen.getByText('Set AutoCount level to 24')).toBeInTheDocument();
    expect(screen.getByText('now 20')).toBeInTheDocument();
  });

  it('confirms a level that still fits, quietly', () => {
    render(<PlanLevelCell suggestion={suggestion({ suggested_level: 20 })} />);

    expect(screen.getByText('Level 20 still fits')).toBeInTheDocument();
  });

  it('opens the arithmetic, which ends at our own orders', () => {
    render(<PlanLevelCell suggestion={suggestion()} />);

    fireEvent.click(screen.getByRole('button', { name: /level suggestion/i }));

    expect(screen.getByText(/Averaged 12 a month over the last 3 months/)).toBeInTheDocument();
    expect(screen.getByText(/rounds up/)).toBeInTheDocument();
    expect(screen.getByText(/Based on our own outgoing orders only/)).toBeInTheDocument();
  });

  it('renders absence when there is no suggestion, never a zero', () => {
    render(<PlanLevelCell suggestion={undefined} />);

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});

describe('the derivation and the amendment (S14)', () => {
  it('graphs the months behind the average, so the sums can be checked at a glance', async () => {
    render(<PlanLevelCell suggestion={suggestion()} />);
    fireEvent.click(screen.getByRole('button', { name: /level suggestion/i }));

    // findBy: the chart arrives through next/dynamic, so it mounts a tick later.
    const chart = await screen.findByTestId('level-chart');
    expect(chart.textContent).toContain('2026-06');
    expect(chart.textContent).toContain('12 12 12');
  });

  it('lets the buyer put their own figure beside the engine’s', async () => {
    const onAmend = vi.fn();
    render(<PlanLevelCell suggestion={suggestion()} onAmend={onAmend} />);
    fireEvent.click(screen.getByRole('button', { name: /level suggestion/i }));

    fireEvent.change(screen.getByLabelText('Your level'), { target: { value: '30' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await vi.waitFor(() => expect(onAmend).toHaveBeenCalledWith(expect.anything(), 30));
  });

  it('typing the engine’s own number back is a withdrawal, not an amendment', async () => {
    const onAmend = vi.fn();
    render(<PlanLevelCell suggestion={suggestion({ amended_level: 30 })} onAmend={onAmend} />);
    fireEvent.click(screen.getByRole('button', { name: /level suggestion/i }));

    fireEvent.change(screen.getByLabelText('Your level'), { target: { value: '24' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await vi.waitFor(() => expect(onAmend).toHaveBeenCalledWith(expect.anything(), null));
  });

  it('an amended row keeps the engine’s number in sight', () => {
    render(<PlanLevelCell suggestion={suggestion({ amended_level: 30 })} />);

    expect(screen.getByText('Set AutoCount level to 30')).toBeInTheDocument();
    expect(screen.getByText(/engine said 24/)).toBeInTheDocument();
  });
});
