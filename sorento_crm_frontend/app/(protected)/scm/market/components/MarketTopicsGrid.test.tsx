/**
 * MarketTopicsGrid - data / empty / error states, client-side search filtering,
 * and the hard-delete confirmation dialog (ConfirmDeleteDialog copy + wiring).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
/* The grace window is the server's; what this file proves is that the row parks one. */
const createPendingAction = vi.fn().mockResolvedValue({
  id: 'pa-1',
  action_key: 'market_topic.delete',
  entity_type: 'market_topic',
  entity_id: 't-copper',
  commit_at: '2026-08-30T10:00:10',
  window_seconds: 10,
});
vi.mock('sonner', () => ({
  // `dismiss` is load-bearing: the countdown's toast is dismissed when the row
  // unmounts, and a stub without it throws out of an effect no assertion catches.
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), dismiss: vi.fn() },
}));

vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// jsdom polyfills for ScrollArea / DataGrid.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/market',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const hooks = vi.hoisted(() => ({
  useMarketTopics: vi.fn(),
  useCreateTopic: vi.fn(),
  useUpdateTopic: vi.fn(),
  useDeleteTopic: vi.fn(),
}));
vi.mock('../hooks/useMarket', () => hooks);

const scmOptions = vi.hoisted(() => ({ useCategoryOptions: vi.fn() }));
vi.mock('../../hooks/useScmOptions', () => scmOptions);

import { MarketTopicsGrid } from './MarketTopicsGrid';
import type { MarketResearchTopic } from '../types/market.types';

function topic(over: Partial<MarketResearchTopic>): MarketResearchTopic {
  return {
    id: 'topic-1',
    label: 'Copper price index',
    category_ref: 'SRT-FC',
    currency: 'MYR',
    search_prompt: 'copper price trend last 30 days',
    cadence: 'weekly',
    is_active: true,
    ...over,
  };
}

const COPPER = topic({ id: 't-copper', label: 'Copper price index' });
const STEEL = topic({ id: 't-steel', label: 'Steel rebar', currency: 'USD', is_active: false });

function mockList(over: Partial<ReturnType<typeof hooks.useMarketTopics>>) {
  hooks.useMarketTopics.mockReturnValue({
    data: undefined, isLoading: false, isError: false, error: null, ...over,
  });
}

const deleteMutate = vi.fn().mockResolvedValue(undefined);

function renderGrid() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MarketTopicsGrid />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  Object.values(hooks).forEach((f) => f.mockReset());
  deleteMutate.mockClear();
  hooks.useCreateTopic.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  hooks.useUpdateTopic.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  hooks.useDeleteTopic.mockReturnValue({ mutateAsync: deleteMutate, isPending: false });
  scmOptions.useCategoryOptions.mockReturnValue({ data: [], isLoading: false });
});

describe('MarketTopicsGrid', () => {
  it('renders data rows with the Add toolbar affordance', () => {
    mockList({ data: [COPPER, STEEL] });
    renderGrid();
    expect(screen.getByText('Copper price index')).toBeInTheDocument();
    expect(screen.getByText('Steel rebar')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Add topic/i })).toBeInTheDocument();
  });

  it('renders active/inactive badges', () => {
    mockList({ data: [COPPER, STEEL] });
    renderGrid();
    // "Active" appears as both the column header and the active-row badge.
    expect(screen.getAllByText('Active').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('Inactive')).toBeInTheDocument();
  });

  it('renders the error banner when the list fails', () => {
    mockList({ isError: true, error: new Error('Failed to load research topics.') });
    renderGrid();
    expect(screen.getByText('Failed to load research topics.')).toBeInTheDocument();
  });

  it('renders the empty message when there are no topics', () => {
    mockList({ data: [] });
    renderGrid();
    expect(screen.getByText('No research topics configured yet.')).toBeInTheDocument();
  });

  it('filters rows by the search box', () => {
    mockList({ data: [COPPER, STEEL] });
    renderGrid();
    fireEvent.change(screen.getByPlaceholderText('Search topics...'), {
      target: { value: 'steel' },
    });
    expect(screen.getByText('Steel rebar')).toBeInTheDocument();
    expect(screen.queryByText('Copper price index')).not.toBeInTheDocument();
  });

  it('parks the delete on the row that was pressed, with no dialog in the way (S6-10)', async () => {
    mockList({ data: [COPPER] });
    renderGrid();
    fireEvent.click(screen.getByRole('button', { name: /Delete topic/i }));

    // D7: the press IS the action, and Cancel in the countdown is the way back.
    await vi.waitFor(() =>
      expect(createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({
          actionKey: 'market_topic.delete',
          entityType: 'market_topic',
          entityId: 't-copper',
        }),
      ),
    );
    expect(deleteMutate).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
