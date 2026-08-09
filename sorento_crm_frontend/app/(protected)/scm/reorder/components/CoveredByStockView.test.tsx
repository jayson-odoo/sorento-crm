import React from 'react';
/**
 * Demand the location's own stock covers is shown, with both numbers the choice needs.
 *
 * > "we can recommend to use stock, but it needs to appear in the reorder planning as a
 * >  suggestion ... never help the user to decide"
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const decideCoveredRow = vi.fn().mockResolvedValue({ choice: 'buy', rec_type: 'buy', status: 'accepted' });
vi.mock('../services/reorderRunService', () => ({
  decideCoveredRow: (...a: unknown[]) => decideCoveredRow(...a),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
import type { ReorderRecommendation } from '../types/reorder.types';
import { CoveredByStockView as Raw } from './CoveredByStockView';

// A query client per render so a mutation in one test cannot leak into the next.
function CoveredByStockView(props: React.ComponentProps<typeof Raw>) {
  return (
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Raw {...props} />
    </QueryClientProvider>
  );
}

beforeEach(() => decideCoveredRow.mockClear());

const row = (over: Partial<ReorderRecommendation> = {}): ReorderRecommendation =>
  ({
    id: 'rec-1',
    type: 'covered',
    sku: 'MWC7624-RL-S10',
    product_name: 'MWC7624-RL-S10',
    warehouse_code: 'BRW',
    order_qty: 1,
    cash_impact: 40,
    covered_committed: 1,
    covered_available: 5,
    reason_label: '5 available in this pool covers 1 committed',
    alternatives: [],
    ...over,
  }) as unknown as ReorderRecommendation;

describe('CoveredByStockView', () => {
  it('states the committed demand and what the location holds', () => {
    render(<CoveredByStockView rows={[row()]} isLoading={false} />);

    expect(screen.getByText('MWC7624-RL-S10')).toBeInTheDocument();
    expect(screen.getByText(/5 available in this pool covers 1 committed/)).toBeInTheDocument();
  });

  it('prices buying anyway, so both sides of the choice are on screen', () => {
    render(<CoveredByStockView rows={[row({ cash_impact: 1250, order_qty: 25 })]} isLoading={false} />);

    expect(screen.getByText('25')).toBeInTheDocument();
    expect(screen.getByText(/1,250/)).toBeInTheDocument();
  });

  it('flags how much of the demand nobody located', () => {
    render(
      <CoveredByStockView rows={[row({ unlocated_demand: 419 })]} isLoading={false} />,
    );

    expect(screen.getByText(/419 unlocated/)).toBeInTheDocument();
  });

  it('says nothing is waiting rather than showing an empty table', () => {
    render(<CoveredByStockView rows={[]} isLoading={false} />);

    expect(screen.getByText(/Nothing is waiting on that choice/i)).toBeInTheDocument();
  });

  it('surfaces a load failure instead of looking like an empty set', () => {
    render(
      <CoveredByStockView
        rows={[]}
        isLoading={false}
        isError
        error={new Error('Failed to load these rows.')}
      />,
    );

    expect(screen.getByText(/Failed to load these rows/i)).toBeInTheDocument();
    expect(screen.queryByText(/Nothing is waiting/i)).not.toBeInTheDocument();
  });
});

describe('deciding a covered row', () => {
  it('offers both choices, never one', () => {
    render(<CoveredByStockView rows={[row()]} isLoading={false} />);

    expect(screen.getByRole('button', { name: /use stock/i })).toBeEnabled();
    expect(screen.getByRole('button', { name: /buy anyway/i })).toBeEnabled();
  });

  it('sends the choice the planner picked', async () => {
    render(<CoveredByStockView rows={[row()]} isLoading={false} runId="run-1" />);

    fireEvent.click(screen.getByRole('button', { name: /buy anyway/i }));

    await waitFor(() => expect(decideCoveredRow).toHaveBeenCalledWith('rec-1', 'buy'));
  });

  it('sends use_stock when that is the choice', async () => {
    render(<CoveredByStockView rows={[row()]} isLoading={false} runId="run-1" />);

    fireEvent.click(screen.getByRole('button', { name: /use stock/i }));

    await waitFor(() => expect(decideCoveredRow).toHaveBeenCalledWith('rec-1', 'use_stock'));
  });
});
