/**
 * The order-trend popup: "who bought it" as a table.
 *
 * > "similar to SO - what is the trend of purchase" (user markup, 2026-08-11) names the
 * >  table shape this mirrors on the buy side; the SO side asked for the same thing first:
 * >  Customer | Qty | Last order date, not a bare list of names.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PlanTrendPopover } from './PlanTrendPopover';
import type { TrajectoryEntry } from '../lib/trajectory';

class ResizeObserverStub { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);

/** Every render of the chart, so the options it was handed can be asserted on. */
const chartRenders = vi.hoisted(
  () => [] as Array<{ options: Record<string, never>; height: number }>,
);

vi.mock('react-apexcharts', () => ({
  default: (props: { options: Record<string, never>; height: number }) => {
    chartRenders.push(props);
    return <div data-testid="trend-chart" />;
  },
}));

const entry = (over: Partial<TrajectoryEntry> = {}): TrajectoryEntry => ({
  verdict: 'rising',
  recent_qty: 120,
  previous_qty: 90,
  change_pct: 33.33,
  year_ago_qty: 200,
  year_change_pct: -40,
  window_months: 12,
  months: [],
  customers: [],
  agents: [],
  agents_available: false,
  ...over,
});

describe('PlanTrendPopover - who bought it', () => {
  it('renders a table with customer, quantity and last order date', () => {
    render(
      <PlanTrendPopover
        trend={entry({
          customers: [
            { customer_name: 'Vivo Homes', qty: 120, last_order_date: '2026-07-12' } as never,
            { customer_name: 'Beta Trading', qty: 40, last_order_date: '2026-06-01' } as never,
          ],
        })}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /order trend/i }));

    expect(screen.getByText('Vivo Homes')).toBeInTheDocument();
    expect(screen.getByText('120')).toBeInTheDocument();
    expect(screen.getByText('12/07/2026')).toBeInTheDocument();
    expect(screen.getByText('Beta Trading')).toBeInTheDocument();
    expect(screen.getByText('01/06/2026')).toBeInTheDocument();
  });

  it('says no orders in the window when nobody bought it', () => {
    render(<PlanTrendPopover trend={entry({ customers: [] })} />);
    fireEvent.click(screen.getByRole('button', { name: /order trend/i }));

    expect(screen.getByText('No orders in the window.')).toBeInTheDocument();
  });

  it('renders a dash for a customer row with no last-order date on record', () => {
    render(
      <PlanTrendPopover
        trend={entry({
          customers: [{ customer_name: 'Unnamed customer', qty: 5, last_order_date: null } as never],
        })}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /order trend/i }));

    expect(screen.getByText('-')).toBeInTheDocument();
  });

  it('renders nothing when no trend information exists for the line', () => {
    render(<PlanTrendPopover trend={undefined} />);

    expect(screen.getByText('No order history')).toBeInTheDocument();
  });
});

describe('PlanTrendPopover - selling price (Fix D, user feedback, 2026-08-12)', () => {
  it('renders the selling price above "Who bought it"', () => {
    render(<PlanTrendPopover trend={entry()} sellingPrice={90} />);
    fireEvent.click(screen.getByRole('button', { name: /order trend/i }));

    expect(screen.getByText('Selling price RM 90.00')).toBeInTheDocument();
  });

  it('omits the line when the selling price is null', () => {
    render(<PlanTrendPopover trend={entry()} sellingPrice={null} />);
    fireEvent.click(screen.getByRole('button', { name: /order trend/i }));

    expect(screen.queryByText(/Selling price/)).not.toBeInTheDocument();
  });

  it('omits the line when no selling price prop is passed at all', () => {
    render(<PlanTrendPopover trend={entry()} />);
    fireEvent.click(screen.getByRole('button', { name: /order trend/i }));

    expect(screen.queryByText(/Selling price/)).not.toBeInTheDocument();
  });
});

describe('PlanTrendPopover - the chart is readable (AC-6)', () => {
  /** Open the popover and hand back the options the chart was rendered with. */
  async function chartOptions() {
    chartRenders.length = 0;
    render(<PlanTrendPopover trend={entry()} />);
    fireEvent.click(screen.getByRole('button', { name: /order trend/i }));
    await screen.findByTestId('trend-chart');
    const last = chartRenders[chartRenders.length - 1];
    expect(last).toBeDefined();
    return last as unknown as {
      height: number;
      options: {
        legend: { position: string; horizontalAlign: string };
        yaxis: { min: number; tickAmount: number; labels: { formatter: (v: number) => string } };
        xaxis: { labels: { rotate: number; hideOverlappingLabels: boolean } };
      };
    };
  }

  it('puts the legend in one row above the plot', async () => {
    // Under the plot it stole height from the only thing worth looking at.
    const { options } = await chartOptions();

    expect(options.legend.position).toBe('top');
    expect(options.legend.horizontalAlign).toBe('left');
  });

  it('gives the plot enough height to read at 12 months', async () => {
    const { height } = await chartOptions();

    expect(height).toBe(240);
  });

  it('quotes the y axis in whole units from zero, at a handful of ticks', async () => {
    // A quantity axis labelled 0.25 / 0.5 is a formatting accident, not a measurement.
    const { options } = await chartOptions();

    expect(options.yaxis.min).toBe(0);
    expect(options.yaxis.tickAmount).toBe(4);
    expect(options.yaxis.labels.formatter(1234)).toBe('1,234');
  });

  it('angles the month labels and drops the ones that would collide', async () => {
    const { options } = await chartOptions();

    expect(options.xaxis.labels.rotate).toBe(-45);
    expect(options.xaxis.labels.hideOverlappingLabels).toBe(true);
  });

  it('overrides the app-wide stacked legend so the two names sit on one row', async () => {
    // `css/components/apexcharts.css` sets `flex-direction: column` on EVERY Apex legend in
    // the app, so `legend.position: 'top'` alone still rendered "This year" and "Last year"
    // on two lines, eating chart height. The override is scoped to this chart's wrapper.
    render(<PlanTrendPopover trend={entry()} />);
    fireEvent.click(screen.getByRole('button', { name: /order trend/i }));
    const chart = await screen.findByTestId('trend-chart');

    const wrapper = chart.parentElement as HTMLElement;
    expect(wrapper.className).toContain('[&_.apexcharts-legend]:flex-row');
  });

  it('renders the popover wide enough for the chart', () => {
    render(<PlanTrendPopover trend={entry()} />);
    fireEvent.click(screen.getByRole('button', { name: /order trend/i }));

    const panel = document.querySelector('[class*="w-\\[30rem\\]"]');
    expect(panel).not.toBeNull();
    expect(panel?.className).toContain('max-w-[92vw]');
  });

  it('drops the "based on our own orders only" footer', () => {
    render(<PlanTrendPopover trend={entry()} />);
    fireEvent.click(screen.getByRole('button', { name: /order trend/i }));

    expect(screen.queryByText(/Based on our own orders only/i)).not.toBeInTheDocument();
  });
});
