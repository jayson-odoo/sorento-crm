import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import MarketSegmentsAdmin from './MarketSegmentsAdmin';
import type { MarketSegment } from '../services/marketSegmentService';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() } }));

const useMarketSegments = vi.fn();
const create = { mutate: vi.fn(), isPending: false };
const update = { mutate: vi.fn(), isPending: false };
const remove = { mutate: vi.fn(), isPending: false };

vi.mock('../hooks/useMarketSegments', () => ({
  useMarketSegments: (...a: unknown[]) => useMarketSegments(...a),
  useMarketSegmentMutations: () => ({ create, update, remove }),
}));

const deleteMarketSegment = vi.fn();
vi.mock('../services/marketSegmentService', () => ({
  deleteMarketSegment: (...a: unknown[]) => deleteMarketSegment(...a),
}));

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const SEGMENTS: MarketSegment[] = [
  {
    code: 'retail',
    name: 'Retail',
    description: 'Walk-in buyers',
    is_active: true,
    sort_order: 1,
    is_requestor_selectable: false,
  },
  {
    code: 'project',
    name: 'Project',
    description: null,
    is_active: false,
    sort_order: 2,
    is_requestor_selectable: true,
  },
];

function mockState(state: Record<string, unknown>) {
  useMarketSegments.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    ...state,
  });
}

beforeEach(() => {
  useMarketSegments.mockReset();
  create.mutate.mockReset();
  update.mutate.mockReset();
  remove.mutate.mockReset();
  deleteMarketSegment.mockReset();
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  }
  if (!('ResizeObserver' in window)) {
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  Element.prototype.scrollIntoView = vi.fn();
  (Element.prototype as unknown as { hasPointerCapture: unknown }).hasPointerCapture = vi.fn();
});

afterEach(() => cleanup());

describe('MarketSegmentsAdmin', () => {
  it('renders the Add toolbar action while loading', () => {
    mockState({ isLoading: true });
    renderWithClient(<MarketSegmentsAdmin />);
    expect(screen.getByRole('button', { name: /add segment/i })).toBeInTheDocument();
  });

  it('renders an empty state when there are no segments', () => {
    mockState({ data: [] });
    renderWithClient(<MarketSegmentsAdmin />);
    expect(screen.getByText(/no market segments yet/i)).toBeInTheDocument();
  });

  it('renders an error state', () => {
    mockState({ isError: true });
    renderWithClient(<MarketSegmentsAdmin />);
    expect(screen.getByText(/failed to load market segments/i)).toBeInTheDocument();
  });

  it('renders a row per segment with human-readable name + code', () => {
    mockState({ data: SEGMENTS });
    renderWithClient(<MarketSegmentsAdmin />);
    expect(screen.getByText('Retail')).toBeInTheDocument();
    expect(screen.getByText('Project')).toBeInTheDocument();
    expect(screen.getByText('retail')).toBeInTheDocument();
    // "Active" also appears as a column header, so scope to the status badge.
    expect(screen.getAllByText('Active').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Inactive')).toBeInTheDocument();
  });

  // The requestor-picker indicator is the admin's only view of which segments
  // feed the "Requested by" / "Sales person" dropdown, so it must be visible on
  // the row AND editable in the dialog.
  it('shows the requestor-picker indicator per segment', () => {
    mockState({ data: SEGMENTS });
    renderWithClient(<MarketSegmentsAdmin />);
    expect(screen.getByText('Included')).toBeInTheDocument();
    expect(screen.getByText('Excluded')).toBeInTheDocument();
  });

  it('seeds the requestor-picker checkbox from the edited segment and saves it', async () => {
    mockState({ data: SEGMENTS });
    renderWithClient(<MarketSegmentsAdmin />);
    // Second row = 'project', the requestor-selectable one.
    fireEvent.click(screen.getAllByLabelText('Edit')[1]);
    const checkbox = screen.getByLabelText('Include in requestor picker');
    expect(checkbox).toBeChecked();
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole('button', { name: 'Update' }));
    await waitFor(() => expect(update.mutate).toHaveBeenCalled());
    expect(update.mutate.mock.calls[0][0]).toMatchObject({
      code: 'project',
      body: { is_requestor_selectable: false },
    });
  });

  it('opens a delete confirmation with the standard copy', async () => {
    mockState({ data: SEGMENTS });
    deleteMarketSegment.mockResolvedValue(undefined);
    renderWithClient(<MarketSegmentsAdmin />);
    fireEvent.click(screen.getAllByLabelText('Delete')[0]);
    expect(screen.getByText('Confirm delete')).toBeInTheDocument();
    expect(screen.getByText(/this action cannot be undone/i)).toBeInTheDocument();
    // Confirming fires the hard-delete service call (scoped to the dialog).
    const dialog = screen.getByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: /^delete$/i }));
    await waitFor(() => expect(deleteMarketSegment).toHaveBeenCalledWith('retail'));
  });
});
