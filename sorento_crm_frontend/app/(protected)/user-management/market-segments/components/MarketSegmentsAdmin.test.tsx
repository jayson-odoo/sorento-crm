import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
/* The grace window is the server's; what this file proves is that the control parks one. */
const createPendingAction = vi.fn().mockResolvedValue({
  id: 'pa-1',
  action_key: 'market_segment.delete',
  entity_type: 'market_segment',
  entity_id: 'retail',
  commit_at: '2026-08-30T10:00:10',
  window_seconds: 10,
});
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import MarketSegmentsAdmin from './MarketSegmentsAdmin';
import type { MarketSegment } from '../services/marketSegmentService';

vi.mock('@/lib/toast', () => ({
  // `dismiss` is load-bearing: the countdown's toast is dismissed when the row
  // unmounts, and a stub without it throws out of an effect no assertion catches.
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), dismiss: vi.fn() },
}));

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

  it('parks the delete on the row that was pressed, keyed by its CODE (S6-10)', async () => {
    mockState({ data: SEGMENTS });
    renderWithClient(<MarketSegmentsAdmin />);
    fireEvent.click(screen.getAllByLabelText('Delete')[0]);

    // D7: the press IS the action. The entity id here is the segment CODE, because
    // that is this table's primary key and what the DELETE route takes.
    await waitFor(() =>
      expect(createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({
          actionKey: 'market_segment.delete',
          entityType: 'market_segment',
          entityId: 'retail',
        }),
      ),
    );
    expect(deleteMarketSegment).not.toHaveBeenCalled();
    expect(screen.queryByText('Confirm delete')).not.toBeInTheDocument();
  });
});
