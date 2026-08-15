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
    },
  ],
  total: 1,
  shown: 1,
  committed_total: 2,
  unlocated_total: 0,
  locations: ['BRW-IB'],
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
    expect(screen.getByText(/sits at BRW-IB/)).toBeInTheDocument();
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

    expect(screen.getByText(/419 named no location/)).toBeInTheDocument();
    expect(screen.getByText('No location')).toBeInTheDocument();
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
});
