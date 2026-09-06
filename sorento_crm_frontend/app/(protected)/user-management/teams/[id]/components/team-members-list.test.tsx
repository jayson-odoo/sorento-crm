import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import TeamMembersList from './team-members-list';
import type { TeamMember } from '../../types/team.types';
import type { UserSelectItem } from '../../services/teamService';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const useTeamMembers = vi.fn();
const removeMutate = vi.fn();
const roundRobinMutate = vi.fn();

vi.mock('../../hooks/use-team-members', () => ({
  useTeamMembers: (...a: unknown[]) => useTeamMembers(...a),
  useRemoveTeamMember: () => ({ mutate: removeMutate, isPending: false }),
  useUpdateTeamMemberRoundRobin: () => ({ mutate: roundRobinMutate, isPending: false }),
}));

vi.mock('../../services/teamService', () => ({ addTeamMember: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function render(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const users: UserSelectItem[] = [
  { id: 'u1', name: 'Agnes', email: 'agnes@e.com' },
];

const member: TeamMember = {
  id: 'm1',
  team_id: 'team-1',
  user_id: 'u1',
  sort_order: 1,
  include_in_round_robin: true,
  created_at: new Date().toISOString(),
};

beforeEach(() => {
  useTeamMembers.mockReset();
  removeMutate.mockReset();
  roundRobinMutate.mockReset();
});

describe('TeamMembersList round-robin toggle', () => {
  it('loading state shows skeletons (no rows)', () => {
    useTeamMembers.mockReturnValue({ data: [], isLoading: true });
    render(<TeamMembersList teamId="team-1" users={users} />);
    expect(screen.getByText('Members')).toBeInTheDocument();
    expect(screen.queryByText('Agnes')).not.toBeInTheDocument();
  });

  it('empty state', () => {
    useTeamMembers.mockReturnValue({ data: [], isLoading: false });
    render(<TeamMembersList teamId="team-1" users={users} />);
    expect(screen.getByText(/No members\./i)).toBeInTheDocument();
  });

  it('renders RR toggle column header and a checked switch by default', () => {
    useTeamMembers.mockReturnValue({ data: [member], isLoading: false });
    render(<TeamMembersList teamId="team-1" users={users} />);
    expect(screen.getByText(/Auto-assign \(round robin\)/i)).toBeInTheDocument();
    const sw = screen.getByLabelText('Include in round robin');
    expect(sw).toBeChecked();
  });

  it('toggling the switch calls the RR mutation', () => {
    useTeamMembers.mockReturnValue({ data: [member], isLoading: false });
    render(<TeamMembersList teamId="team-1" users={users} />);
    fireEvent.click(screen.getByLabelText('Include in round robin'));
    expect(roundRobinMutate).toHaveBeenCalledWith({ userId: 'u1', includeInRoundRobin: false });
  });
});
