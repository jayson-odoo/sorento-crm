/**
 * FILTER-MULTISELECT PR2 review: Team pending's Team options come from the response's `teams` (every team
 * the caller can see), not from the rows on the page: a team with no rows is still offered, and a team
 * filter leaves both offered. Harness mirrors TeamPendingList.multiFilters.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import TeamPendingList from './TeamPendingList';
import type { TeamPendingItem } from '@/app/(protected)/sla-management/conversation-sla-tracking/services/conversationSLATrackingService';

vi.mock('next/navigation', () => ({ usePathname: () => '/sla-management/team-pending' }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, placeholder }: Props) => (
    <select multiple aria-label={placeholder ?? 'multi'} value={value}
      onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
      {(options ?? []).map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

function render(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const useTeamPendingSLA = vi.fn();
const useVisibleUsers = vi.fn();

vi.mock('@/app/(protected)/sla-management/conversation-sla-tracking/hooks/useTeamPendingSLA', () => ({
  useTeamPendingSLA: (...a: unknown[]) => useTeamPendingSLA(...a),
  useVisibleUsers: (...a: unknown[]) => useVisibleUsers(...a),
  useTakeoverSLATracking: () => ({ mutate: vi.fn(), isPending: false, variables: undefined }),
  useReassignSLATracking: () => ({ mutate: vi.fn(), isPending: false, variables: undefined }),
}));
vi.mock('@/app/(protected)/account/notifications/hooks/useCoverage', () => ({
  useSubscribeCoverage: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const mk = (id: string, assignee: string, team: string): TeamPendingItem => ({
  id,
  assignee_id: `u-${assignee}`,
  assignee_name: assignee,
  team_id: `team-${team}`,
  team_label: `Team ${team}`,
  source_entity_type: 'complaint',
  source_entity_id: `cmp-${id}`,
  is_form_sla: true,
  reference: `CMP-${id}`,
  respond_io_id: null,
  due_at: new Date(Date.now() + 3600_000).toISOString(),
  is_responded: false,
  current_tier: 1,
  policy_name: 'Default policy',
  next_action: 'Approve',
});


const TEAMS = [
  { id: 'team-A', name: 'Team A' },
  { id: 'team-B', name: 'Team B' },
];
const lastArgs = () => {
  const calls = useTeamPendingSLA.mock.calls;
  return calls[calls.length - 1][0] as Record<string, string | undefined>;
};

beforeEach(() => {
  useTeamPendingSLA.mockReset();
  useVisibleUsers.mockReset();
  useVisibleUsers.mockReturnValue({ data: [{ id: 'u-Ann', name: 'Ann', email: 'ann@e.com' }] });
  // Rows only in team A; the response still lists both visible teams, whatever filter is applied.
  useTeamPendingSLA.mockReturnValue({
    data: { data: [mk('1', 'Ann', 'A')], teams: TEAMS, total: 1, page: 1, limit: 50 },
    isLoading: false,
    isFetching: false,
    refetch: vi.fn(),
  });
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    })) as unknown as typeof window.matchMedia;
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

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  render(<TeamPendingList />);
  await screen.findByText('CMP-1');
  await user.click(screen.getByRole('button', { name: /^filters/i }));
}
const teamBox = async () => {
  const boxes = await screen.findAllByRole('listbox');
  return boxes[1] as HTMLSelectElement;
};
const offered = (box: HTMLSelectElement) => Array.from(box.options).map((o) => o.textContent);

describe('Team pending - Team options', () => {
  it('offers a team that has no rows on the page', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const box = await teamBox();
    expect(offered(box)).toEqual(['Team A', 'Team B']);
  });

  it('keeps both teams offered after a team is chosen', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await teamBox(), ['team-A']);
    await waitFor(() => expect(lastArgs().team).toBe('team-A'));
    expect(offered(await teamBox())).toEqual(['Team A', 'Team B']);
  });
});
