/**
 * Which orders a planned quantity is actually for.
 *
 * > "my demand is at brw-ib wor, why it is bought to brw leh, why order so many leh"
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const useRecommendationDemand = vi.fn();
vi.mock('../hooks/useReorderRun', () => ({
  useRecommendationDemand: (...a: unknown[]) => useRecommendationDemand(...a),
}));

import { PlanDemandPopover } from './PlanDemandPopover';

const demand = (over: Record<string, unknown> = {}) => ({
  lines: [
    {
      so_number: 'SO414050',
      warehouse_code: 'BRW-IB',
      is_unlocated: false,
      order_type: 'project',
      demand_class: 'project',
      order_date: '2026-07-27',
      required_date: '2026-10-12',
      qty: 2,
      customer_label: 'Vivo Homes Sdn Bhd',
      unit_price: 94.5,
    },
  ],
  total: 1,
  shown: 1,
  committed_total: 2,
  unlocated_total: 0,
  locations: ['BRW-IB'],
  scope: 'warehouse',
  pool_code: null,
  ...over,
});

function stub(data: unknown, extra: Record<string, unknown> = {}) {
  useRecommendationDemand.mockReturnValue({
    data,
    isLoading: false,
    isError: false,
    error: null,
    ...extra,
  });
}

beforeEach(() => useRecommendationDemand.mockReset());

async function open() {
  fireEvent.click(screen.getByRole('button', { name: /demand behind this row/i }));
  await waitFor(() => expect(screen.getByText(/Demand behind this row/)).toBeInTheDocument());
}

describe('PlanDemandPopover', () => {
  it('does not fetch until it is opened', async () => {
    // The query lives inside the opened panel, so a closed row holds no subscription at
    // all - on a full plan that is hundreds of them for panels nobody opened.
    stub(demand());
    render(<PlanDemandPopover runId="run-1" recId="rec-1" />);

    expect(useRecommendationDemand).not.toHaveBeenCalled();

    await open();
    expect(useRecommendationDemand).toHaveBeenCalledWith('run-1', 'rec-1', true);
  });

  it('names the location the ORDER was for, which is the whole question', async () => {
    stub(demand());
    render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
    await open();

    expect(screen.getByText('SO414050')).toBeInTheDocument();
    expect(screen.getByText('BRW-IB')).toBeInTheDocument();
    expect(screen.getByText('2 committed at BRW-IB')).toBeInTheDocument();
  });

  it('names the POOL when the plan netted the pool together', async () => {
    // AC-1.2: the number is still the row's own, but it was built over the pool, and a
    // list of siblings the buyer never ordered for has to say why it is there.
    stub(
      demand({
        committed_total: 6683,
        locations: ['BRW-BB', 'BRW-IB'],
        scope: 'pool',
        pool_code: 'BRW',
      }),
    );
    render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
    await open();

    expect(
      screen.getByText('6,683 committed at BRW-BB, BRW-IB (pool BRW)'),
    ).toBeInTheDocument();
  });

  it('says which part of it nobody located', async () => {
    stub(
      demand({
        unlocated_total: 419,
        committed_total: 420,
        locations: ['BRW-IB', 'No location'],
        lines: [{ ...demand().lines[0], warehouse_code: null, is_unlocated: true, qty: 419 }],
      }),
    );
    render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
    await open();

    expect(
      screen.getByText('420 committed at BRW-IB, No location, incl. 419 unlocated'),
    ).toBeInTheDocument();
    expect(screen.getByText('No location')).toBeInTheDocument();
  });

  it('names who ordered each line, and what they pay', async () => {
    stub(demand());
    render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
    await open();

    expect(screen.getByText('Vivo Homes Sdn Bhd')).toBeInTheDocument();
    expect(screen.getByText('RM 94.50')).toBeInTheDocument();
  });

  it('keeps the honest fallbacks the backend sends, and shows no price when there is none', async () => {
    // "Unnamed customer" is retired: a debtor code IS an attribution, and an order that
    // names nobody is a fact about the order rather than a missing value.
    stub(
      demand({
        lines: [
          { ...demand().lines[0], customer_label: 'Debtor 300-R009', unit_price: null },
        ],
      }),
    );
    render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
    await open();

    expect(screen.getByText('Debtor 300-R009')).toBeInTheDocument();
    expect(screen.queryByText(/^RM /)).not.toBeInTheDocument();
  });

  it('distinguishes project from retail', async () => {
    stub(demand({ lines: [{ ...demand().lines[0], order_type: 'retail' }] }));
    render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
    await open();

    expect(screen.getByText('retail')).toBeInTheDocument();
  });

  it('says a forecast-raised buy has no order behind it, rather than showing nothing', async () => {
    stub(demand({ lines: [], total: 0, shown: 0, committed_total: 0, locations: [] }));
    render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
    await open();

    expect(screen.getByText(/raised from forecast demand/i)).toBeInTheDocument();
  });

  // SF-8: the source chip (SO / OI / OI confirmed) and its title, per line.
  describe('source chip', () => {
    it('renders SO with "Direct sales order" for a direct sales-order line', async () => {
      stub(demand({ lines: [{ ...demand().lines[0], source: 'sales_order' }] }));
      render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
      await open();

      const chip = screen.getByText('SO');
      expect(chip).toBeInTheDocument();
      expect(chip).toHaveAttribute('title', 'Direct sales order');
    });

    it('renders OI with "From an Order Inquiry (project channel)" for an order-inquiry line', async () => {
      stub(demand({ lines: [{ ...demand().lines[0], source: 'order_inquiry' }] }));
      render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
      await open();

      const chip = screen.getByText('OI');
      expect(chip).toBeInTheDocument();
      expect(chip).toHaveAttribute('title', 'From an Order Inquiry (project channel)');
    });

    it('renders "OI confirmed" with "Confirmed for buy by CS" for a CS-confirmed line', async () => {
      stub(demand({ lines: [{ ...demand().lines[0], source: 'order_inquiry_confirmed' }] }));
      render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
      await open();

      const chip = screen.getByText('OI confirmed');
      expect(chip).toBeInTheDocument();
      expect(chip).toHaveAttribute('title', 'Confirmed for buy by CS');
    });

    it('renders no chip at all when the line carries no source', async () => {
      stub(demand({ lines: [{ ...demand().lines[0], source: null }] }));
      render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
      await open();

      expect(screen.queryByText('SO')).not.toBeInTheDocument();
      expect(screen.queryByText('OI')).not.toBeInTheDocument();
      expect(screen.queryByText('OI confirmed')).not.toBeInTheDocument();
    });
  });

  // SF-8 / N-6: the channel-split totals line under the scope sentence.
  describe('the totals line (project/retail/unclassified split)', () => {
    it('renders the split when the payload carries any of the three totals', async () => {
      stub(demand({ project_total: 6, retail_total: 4, unclassified_total: 0 }));
      render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
      await open();

      expect(screen.getByText('Project 6 - Retail 4')).toBeInTheDocument();
    });

    it('adds the Unclassified part only when it is nonzero', async () => {
      stub(demand({ project_total: 6, retail_total: 4, unclassified_total: 3 }));
      render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
      await open();

      expect(screen.getByText('Project 6 - Retail 4 - Unclassified 3')).toBeInTheDocument();
    });

    it('hides the totals line entirely on a legacy payload carrying none of the three fields', async () => {
      // `demand()` is the legacy fixture shape - no project_total/retail_total/unclassified_total.
      stub(demand());
      render(<PlanDemandPopover runId="run-1" recId="rec-1" />);
      await open();

      expect(screen.queryByText(/^Project /)).not.toBeInTheDocument();
    });
  });
});
