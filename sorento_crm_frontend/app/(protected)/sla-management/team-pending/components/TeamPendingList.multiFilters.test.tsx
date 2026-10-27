/**
 * FILTER-MULTISELECT PR2: Team pending's Assignee and Team filters take several values (OR within a
 * filter, AND across), one comma-joined param each. Harness mirrors TeamPendingList.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, waitFor, within } from '@testing-library/react';
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

const lastArgs = () => {
  const calls = useTeamPendingSLA.mock.calls;
  return calls[calls.length - 1][0] as Record<string, string | undefined>;
};
const filtersButton = () => screen.getByRole('button', { name: /^filters/i });

beforeEach(() => {
  useTeamPendingSLA.mockReset();
  useVisibleUsers.mockReset();
  useVisibleUsers.mockReturnValue({
    data: [
      { id: 'u-Ann', name: 'Ann', email: 'ann@e.com' },
      { id: 'u-Ben', name: 'Ben', email: 'ben@e.com' },
      { id: 'u-Cat', name: 'Cat', email: 'cat@e.com' },
    ],
  });
  useTeamPendingSLA.mockReturnValue({
    data: { data: [mk('1', 'Ann', 'A'), mk('2', 'Ben', 'B'), mk('3', 'Cat', 'C')], total: 3, page: 1, limit: 50 },
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
  await user.click(filtersButton());
}

describe('Team pending - multi Assignee and Team filters', () => {
  it('are two multi controls, Assignee then Team', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    expect(boxes).toHaveLength(2);
    for (const box of boxes) expect(box.hasAttribute('multiple')).toBe(true);
  });

  it('two assignees go to the hook comma-joined and the badge counts one filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const [assignee] = await screen.findAllByRole('listbox');
    await user.selectOptions(assignee, ['u-Ann', 'u-Ben']);
    await waitFor(() => expect(lastArgs().assignee).toBe('u-Ann,u-Ben'));
    expect(lastArgs().team).toBeUndefined();
    await user.keyboard('{Escape}');
    await waitFor(() => expect(within(filtersButton()).getByText('1')).toBeInTheDocument());
  });

  it('two teams go to the hook comma-joined', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    await user.selectOptions(boxes[1], ['team-A', 'team-B']);
    await waitFor(() => expect(lastArgs().team).toBe('team-A,team-B'));
  });

  it('the filters AND across each other and Clear filters drops both', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    await user.selectOptions(boxes[0], ['u-Ann', 'u-Ben']);
    await user.selectOptions(boxes[1], ['team-A', 'team-B']);
    await waitFor(() => expect(lastArgs()).toMatchObject({ assignee: 'u-Ann,u-Ben', team: 'team-A,team-B' }));
    await user.click(screen.getByRole('button', { name: /clear filters/i }));
    await waitFor(() => expect(lastArgs().assignee).toBeUndefined());
    expect(lastArgs().team).toBeUndefined();
  });
});
