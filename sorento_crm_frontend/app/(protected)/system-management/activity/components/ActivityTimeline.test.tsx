import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ActivityTimeline from './ActivityTimeline';
import { ENTITY_TYPE_OPTIONS, entityTypeLabel } from './activityPresenters';
import type { ActivityItem } from '../types/activity.types';

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const useActivityFeed = vi.fn();

vi.mock('../hooks/useActivityFeed', () => ({
  useActivityFeed: (...a: unknown[]) => useActivityFeed(...a),
}));

beforeEach(() => {
  useActivityFeed.mockReset();
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
});

afterEach(() => cleanup());

const ITEM: ActivityItem = {
  id: 'a-1',
  entity_type: 'complaint',
  entity_label: 'Complaint CMP-1042',
  entity_href: '/complaint-management/complaints/abc-123',
  action: 'updated',
  actor_name: 'Jane Tan',
  changed_at: '2026-06-30T09:00:00Z',
  summary: 'Status: Pending → Resolved',
  changes: [{ field: 'Status', from: 'Pending', to: 'Resolved' }],
  trace_id: null,
};

function mockState(state: Record<string, unknown>) {
  useActivityFeed.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    isFetching: false,
    ...state,
  });
}

describe('ActivityTimeline', () => {
  it('renders the search affordance while loading', () => {
    mockState({ isLoading: true });
    renderWithClient(<ActivityTimeline />);
    expect(screen.getByPlaceholderText(/search activity/i)).toBeInTheDocument();
  });

  it('renders an empty state when there is no activity', () => {
    mockState({
      data: { items: [], actors: [], pagination: { total: 0, page: 1, limit: 50 } },
    });
    renderWithClient(<ActivityTimeline />);
    expect(screen.getByText(/no activity recorded yet/i)).toBeInTheDocument();
  });

  it('renders a resolved entity label (never a UUID) with its change diff', () => {
    mockState({
      data: {
        items: [ITEM],
        actors: [{ id: 'u1', name: 'Jane Tan' }],
        pagination: { total: 1, page: 1, limit: 50 },
      },
    });
    renderWithClient(<ActivityTimeline />);
    expect(screen.getByText('Complaint CMP-1042')).toBeInTheDocument();
    expect(screen.getByText('Resolved')).toBeInTheDocument();
    expect(screen.getByText('Jane Tan')).toBeInTheDocument();
    expect(screen.queryByText('abc-123')).not.toBeInTheDocument();
  });

  it('can filter to customers, and labels them without a raw id', () => {
    // Customers became audited without joining the timeline's entity registry, so
    // their rows read "Customer 3f2a1b9c" and could not be filtered for at all.
    expect(ENTITY_TYPE_OPTIONS).toContainEqual({
      value: 'customer',
      label: 'Customer',
    });
    expect(entityTypeLabel('customer')).toBe('Customer');
  });

  it('renders an error state with a retry affordance', () => {
    mockState({ isError: true, error: new Error('Failed to load activity timeline') });
    renderWithClient(<ActivityTimeline />);
    expect(screen.getByText('Failed to load activity timeline.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('no longer renders the Phase-1 demo state switcher', () => {
    mockState({
      data: { items: [], actors: [], pagination: { total: 0, page: 1, limit: 50 } },
    });
    renderWithClient(<ActivityTimeline />);
    expect(screen.queryByText(/demo: data/i)).not.toBeInTheDocument();
  });
});
