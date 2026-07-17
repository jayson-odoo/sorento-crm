/**
 * MarketTopicsGrid — data / empty / error states, client-side search filtering,
 * and the hard-delete confirmation dialog (ConfirmDeleteDialog copy + wiring).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, fireEvent } from '@testing-library/react';
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

  it('opens the hard-delete confirmation with the standard copy + topic name', async () => {
    mockList({ data: [COPPER, STEEL] });
    renderGrid();
    fireEvent.click(screen.getAllByRole('button', { name: /Delete topic/i })[0]);
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Confirm delete')).toBeInTheDocument();
    expect(within(dialog).getByText(/This action cannot be undone/i)).toBeInTheDocument();
    expect(within(dialog).getByText('Copper price index')).toBeInTheDocument();
  });

  it('calls the delete mutation with the row id on confirm', async () => {
    mockList({ data: [COPPER] });
    renderGrid();
    fireEvent.click(screen.getByRole('button', { name: /Delete topic/i }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: /^Delete$/i }));
    await vi.waitFor(() => expect(deleteMutate).toHaveBeenCalledWith('t-copper'));
  });
});
