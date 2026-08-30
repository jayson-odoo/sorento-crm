import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { NeedsLevelView } from './NeedsLevelView';
import type { ReorderRecommendation } from '../types/reorder.types';

const acceptSuggestedLevel = vi.fn();
vi.mock('../services/reorderRunService', () => ({
  acceptSuggestedLevel: (...a: unknown[]) => acceptSuggestedLevel(...a),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/hooks/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ isLoading: false, columnOrder: [], columnVisibility: {} }),
}));

function row(over: Partial<ReorderRecommendation> = {}): ReorderRecommendation {
  return {
    id: 'r1',
    type: 'needs_level',
    sku: 'SKU-1',
    product_name: 'Widget',
    product_id: 'p1',
    warehouse_id: 'w1',
    warehouse_code: 'BRW-IB',
    segment: 'project',
    on_hand: 8,
    outstanding_sales: 2,
    suggested_level: 80,
    suggestion_basis: { adu: 1.333, lead_time_days: 30, safety_days: 14, window_days: 90,
                        window_qty: 120, no_movement: false },
    reason_label: 'no reorder level set',
    rank: null,
    ...over,
  } as unknown as ReorderRecommendation;
}

function renderView(rows: ReorderRecommendation[], props = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <NeedsLevelView rows={rows} isLoading={false} runId="run-1" {...props} />
    </QueryClientProvider>,
  );
}

describe('NeedsLevelView', () => {
  beforeEach(() => {
    acceptSuggestedLevel.mockReset();
    acceptSuggestedLevel.mockResolvedValue({ level: 80, source: 'accepted_suggestion' });
  });

  it('shows a skeleton while loading', () => {
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <NeedsLevelView rows={[]} isLoading runId="run-1" />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId('needs-level-loading')).toBeInTheDocument();
  });

  it('says every item has a level rather than rendering an empty table', () => {
    renderView([]);
    expect(screen.getByText(/every item in this plan has a level/i)).toBeInTheDocument();
  });

  it('surfaces a load error', () => {
    renderView([], { isError: true, error: new Error('boom') });
    expect(screen.getByText('boom')).toBeInTheDocument();
  });

  it('shows the arithmetic behind the suggestion, not just the number', () => {
    renderView([row()]);
    expect(screen.getByText(/1.333 a day x 30 day lead \+ 14 days safety/i)).toBeInTheDocument();
  });

  it('says nothing moved rather than showing an unexplained zero', () => {
    renderView([
      row({
        suggested_level: 0,
        suggestion_basis: { window_days: 90, no_movement: true },
      }),
    ]);
    expect(screen.getByText(/nothing moved in 90 days/i)).toBeInTheDocument();
  });

  it('accepts the suggestion for the row product and location', async () => {
    renderView([row()]);
    fireEvent.click(screen.getAllByRole('button', { name: /accept/i }).at(-1)!);
    await waitFor(() => expect(acceptSuggestedLevel).toHaveBeenCalledWith('p1', 'w1'));
  });

  it('marks the row as set so the click is visibly acknowledged', async () => {
    renderView([row()]);
    fireEvent.click(screen.getAllByRole('button', { name: /accept/i }).at(-1)!);
    await waitFor(() => expect(screen.getByRole('button', { name: /level set/i })).toBeDisabled());
  });

  it('counts how many are still to set', () => {
    renderView([row(), row({ id: 'r2', sku: 'SKU-2' })]);
    expect(screen.getByText(/2 still to set of 2/i)).toBeInTheDocument();
  });
});
