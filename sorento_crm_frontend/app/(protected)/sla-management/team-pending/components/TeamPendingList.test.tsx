import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import TeamPendingList from './TeamPendingList';
import type { TeamPendingItem } from '@/app/(protected)/sla-management/conversation-sla-tracking/services/conversationSLATrackingService';

vi.mock('next/navigation', () => ({ usePathname: () => '/sla-management/team-pending' }));

// DataGrid persists column prefs via this hook (fires network) - stub it.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

function render(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const useTeamPendingSLA = vi.fn();
const useVisibleUsers = vi.fn();
const takeoverMutate = vi.fn();
const reassignMutate = vi.fn();
const subscribeMutate = vi.fn();

vi.mock('@/app/(protected)/sla-management/conversation-sla-tracking/hooks/useTeamPendingSLA', () => ({
  useTeamPendingSLA: (...a: unknown[]) => useTeamPendingSLA(...a),
  useVisibleUsers: (...a: unknown[]) => useVisibleUsers(...a),
  useTakeoverSLATracking: () => ({ mutate: takeoverMutate, isPending: false, variables: undefined }),
  useReassignSLATracking: () => ({ mutate: reassignMutate, isPending: false, variables: undefined }),
}));

vi.mock('@/app/(protected)/account/notifications/hooks/useCoverage', () => ({
  useSubscribeCoverage: () => ({ mutate: subscribeMutate, isPending: false }),
}));

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const row: TeamPendingItem = {
  id: 't1',
  assignee_id: 'u-charissa',
  assignee_name: 'Charissa',
  team_id: 'team-1',
  team_label: 'Marketing - Product',
  source_entity_type: 'complaint',
  source_entity_id: 'cmp-1',
  is_form_sla: true,
  reference: 'CMP-0001',
  respond_io_id: null,
  due_at: new Date(Date.now() + 3600_000).toISOString(),
  is_responded: false,
  current_tier: 2,
  policy_name: 'Default policy',
  next_action: 'Approve',
};

beforeEach(() => {
  useTeamPendingSLA.mockReset();
  useVisibleUsers.mockReset();
  takeoverMutate.mockReset();
  reassignMutate.mockReset();
  subscribeMutate.mockReset();
  useVisibleUsers.mockReturnValue({ data: [{ id: 'u-charissa', name: 'Charissa', email: 'c@e.com' }] });
});

describe('TeamPendingList', () => {
  it('loading state', () => {
    useTeamPendingSLA.mockReturnValue({ data: undefined, isLoading: true, isFetching: true, refetch: vi.fn() });
    render(<TeamPendingList />);
    // DataGrid renders the canonical toolbar even while loading.
    expect(screen.getByRole('button', { name: /filters/i })).toBeInTheDocument();
  });

  it('empty state', () => {
    useTeamPendingSLA.mockReturnValue({
      data: { data: [], total: 0, page: 1, limit: 50, empty: true },
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    render(<TeamPendingList />);
    expect(screen.getByText(/No open tasks across your teams/i)).toBeInTheDocument();
  });

  it('renders rows with assignee name and team (no UUIDs)', () => {
    useTeamPendingSLA.mockReturnValue({
      data: { data: [row], total: 1, page: 1, limit: 50, empty: false },
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    render(<TeamPendingList />);
    expect(screen.getByText('CMP-0001')).toBeInTheDocument();
    expect(screen.getByText('Charissa')).toBeInTheDocument();
    expect(screen.getByText('Marketing - Product')).toBeInTheDocument();
    expect(screen.queryByText('u-charissa')).not.toBeInTheDocument();
    expect(screen.queryByText('team-1')).not.toBeInTheDocument();
  });

  it('Takeover calls the mutation with the row team id', () => {
    useTeamPendingSLA.mockReturnValue({
      data: { data: [row], total: 1, page: 1, limit: 50, empty: false },
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    render(<TeamPendingList />);
    fireEvent.click(screen.getByRole('button', { name: /^Takeover$/i }));
    expect(takeoverMutate).toHaveBeenCalledWith({ id: 't1', teamId: 'team-1' });
  });

  it('Cover for subscribes to the assignee', () => {
    useTeamPendingSLA.mockReturnValue({
      data: { data: [row], total: 1, page: 1, limit: 50, empty: false },
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    render(<TeamPendingList />);
    fireEvent.click(screen.getByRole('button', { name: /Cover for Charissa/i }));
    expect(subscribeMutate).toHaveBeenCalledWith(
      { targetUserId: 'u-charissa' },
      expect.anything(),
    );
  });

  it('Reassign opens the picker dialog', async () => {
    useTeamPendingSLA.mockReturnValue({
      data: { data: [row], total: 1, page: 1, limit: 50, empty: false },
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    });
    render(<TeamPendingList />);
    fireEvent.click(screen.getByRole('button', { name: /^Reassign$/i }));
    await waitFor(() => expect(screen.getByText('Reassign task')).toBeInTheDocument());
  });
});
