/**
 * The team's own page, `/sales/teams/{id}` (UAC S6-13, S6-15; owner ruling 26 Sep 06:01
 * (Lavish) N5 and 26 Sep 06:09 T2).
 *
 * Header: the team name, Active badge and agent count in the meta strip, Edit, Delete in the
 * gear (deferred), prev/next. One section in this lane, always rendered: **Agents** (the Team
 * targets section arrives with S1). An agent who left this month keeps a muted line with a
 * "Left 14 Oct" pill. Edit changes the name in place and adds Add agents and a remove control
 * on each row; nothing moves.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  usePathname: () => '/sales/teams/north',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/components/common/DetailActions', () => ({
  default: ({
    pagerNode,
    primary,
    pendingAction,
  }: {
    pagerNode?: React.ReactNode;
    primary?: React.ReactNode;
    pendingAction?: React.ReactNode;
  }) => (
    <div data-testid="detail-actions">
      {pagerNode}
      {pendingAction ?? primary}
    </div>
  ),
}));

vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: (props: {
    value: string[];
    onChange: (v: string[]) => void;
    options?: { value: string; label: string }[];
  }) => (
    <fieldset aria-label="Add agents">
      {(props.options ?? []).map((o) => (
        <label key={o.value}>
          <input
            type="checkbox"
            checked={props.value.includes(o.value)}
            onChange={(e) =>
              props.onChange(
                e.target.checked
                  ? [...props.value, o.value]
                  : props.value.filter((v) => v !== o.value),
              )
            }
          />
          {o.label}
        </label>
      ))}
    </fieldset>
  ),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    value: string;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
    clearable?: boolean;
  }) => (
    <select
      id={props.id}
      data-clearable={props.clearable ? 'true' : 'false'}
      value={props.value}
      onChange={(e) => props.onChange(e.target.value)}
    >
      <option value="">No leader</option>
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

const perms = vi.hoisted(() => ({ granted: new Set<string>() }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => perms.granted.has(slug),
}));

const save = vi.hoisted(() => ({ mutateAsync: vi.fn(), isPending: false }));
const hooks = vi.hoisted(() => ({
  useSalesTeam: vi.fn(),
  useSalesTeams: vi.fn(),
  useSalesTeamAgentOptions: vi.fn(),
  useSaveSalesTeam: () => save,
}));
vi.mock('../../hooks/useSalesTeams', () => hooks);
vi.mock('../../actions', () => ({
  useSalesTeamActions: () => ({ actions: [], dialogs: null, pending: null }),
}));

import { SalesTeamDetail } from './SalesTeamDetail';
import type { SalesTeamDetail as Detail } from '../../types/salesTeam.types';

function detail(over: Partial<Detail> = {}): Detail {
  return {
    id: 'north',
    name: 'North',
    is_active: true,
    leader_sales_agent_id: null,
    leader_label: null,
    member_count: 2,
    on: '2026-10-20',
    members: [
      member('ali', 'ALI - Ali Hassan'),
      member('mei', 'MEI - Tan Mei Ling'),
      { ...member('kim', 'KIM - Kim Tan'), valid_to: '2026-10-14', left: true },
    ],
    moved: [],
    created_at: '2026-09-26T01:00:00',
    updated_at: '2026-09-30T01:00:00',
    ...over,
  };
}

function member(id: string, label: string) {
  return {
    sales_agent_id: id,
    code: label.split(' - ')[0],
    name: label.split(' - ')[1],
    label,
    valid_from: null,
    valid_to: null,
    left: false,
  };
}

beforeEach(() => {
  perms.granted = new Set(['sales.teams.view', 'sales.teams.edit', 'sales.teams.delete']);
  save.mutateAsync.mockReset();
  save.mutateAsync.mockResolvedValue({});
  hooks.useSalesTeam.mockReturnValue({ data: detail(), isLoading: false, isError: false });
  hooks.useSalesTeams.mockReturnValue({
    data: { data: [{ id: 'central' }, { id: 'north' }, { id: 'south' }] },
    isLoading: false,
  });
  hooks.useSalesTeamAgentOptions.mockReturnValue({
    data: [
      { id: 'ali', code: 'ALI', label: 'ALI - Ali Hassan', team_id: 'north', team_name: 'North' },
      { id: 'sean', code: 'SEAN I', label: 'SEAN I - Sean Lee', team_id: 'central', team_name: 'Central' },
      { id: 'raj', code: 'RAJ', label: 'RAJ - Raj Kumar', team_id: null, team_name: null },
    ],
    isLoading: false,
  });
});

describe('SalesTeamDetail', () => {
  it('heads the page with the name, Active badge and agent count, plus prev/next', () => {
    render(<SalesTeamDetail id="north" />);
    expect(screen.getByRole('heading', { name: 'North' })).toBeTruthy();
    expect(screen.getByText('Active')).toBeTruthy();
    expect(screen.getByText('2 agents')).toBeTruthy();
    expect(screen.getByText('1 left this month')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Previous sales team' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Next sales team' })).toBeTruthy();
    // RecordNavigation's index is 1-based: North is 2nd of central/north/south.
    expect(screen.getByText('2 / 3')).toBeTruthy();
  });

  it('shows the first team as "1 / 3", not "- / 3"', () => {
    hooks.useSalesTeam.mockReturnValue({
      data: detail({ id: 'central', name: 'Central' }),
      isLoading: false,
      isError: false,
    });
    render(<SalesTeamDetail id="central" />);
    expect(screen.getByText('1 / 3')).toBeTruthy();
  });

  it('lists the agents, and keeps a muted "Left 14 Oct" line for one who left', () => {
    render(<SalesTeamDetail id="north" />);
    const agents = screen.getByRole('region', { name: 'Agents' });
    expect(within(agents).getByText('ALI - Ali Hassan')).toBeTruthy();
    expect(within(agents).getByText('MEI - Tan Mei Ling')).toBeTruthy();
    const kim = within(agents).getByText('KIM - Kim Tan');
    expect(within(agents).getByText('Left 14 Oct')).toBeTruthy();
    expect(kim.closest('[data-left="true"]')).not.toBeNull();
  });

  it('has no Team targets section before S1', () => {
    render(<SalesTeamDetail id="north" />);
    expect(screen.queryByText(/team targets/i)).toBeNull();
  });

  it('shows "No agents in this team" with Add agents when empty', () => {
    hooks.useSalesTeam.mockReturnValue({
      data: detail({ member_count: 0, members: [] }),
      isLoading: false,
      isError: false,
    });
    render(<SalesTeamDetail id="north" />);
    const agents = screen.getByRole('region', { name: 'Agents' });
    expect(within(agents).getByText('No agents in this team')).toBeTruthy();
    fireEvent.click(within(agents).getByRole('button', { name: /add agents/i }));
    // Add agents opens the edit session with the picker in the section, in place.
    expect(screen.getByRole('group', { name: 'Add agents' })).toBeTruthy();
  });

  it('edits in place: the name becomes an input, rows gain a remove control, save sends the new list', async () => {
    render(<SalesTeamDetail id="north" />);
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));

    const name = screen.getByLabelText('Team name') as HTMLInputElement;
    expect(name.value).toBe('North');
    fireEvent.change(name, { target: { value: 'North East' } });

    fireEvent.click(screen.getByRole('button', { name: 'Remove MEI - Tan Mei Ling' }));
    // A member who already left has nothing to remove.
    expect(screen.queryByRole('button', { name: 'Remove KIM - Kim Tan' })).toBeNull();

    fireEvent.click(screen.getByLabelText('SEAN I - Sean Lee (now in Central)'));
    const movesOn = screen.getByLabelText('Moves on') as HTMLInputElement;
    fireEvent.change(movesOn, { target: { value: '2026-10-15' } });

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(save.mutateAsync).toHaveBeenCalledTimes(1));
    expect(save.mutateAsync).toHaveBeenCalledWith({
      teamId: 'north',
      name: 'North East',
      is_active: true,
      sales_agent_ids: ['ali', 'sean'],
      moves_on: '2026-10-15',
      leader_sales_agent_id: null,
    });
  });

  it('names the leader in the header and tags their row (W1)', () => {
    hooks.useSalesTeam.mockReturnValue({
      data: detail({ leader_sales_agent_id: 'mei', leader_label: 'MEI - Tan Mei Ling' }),
      isLoading: false,
      isError: false,
    });
    render(<SalesTeamDetail id="north" />);
    expect(screen.getByText('Leader: MEI - Tan Mei Ling')).toBeTruthy();
    const agents = screen.getByRole('region', { name: 'Agents' });
    const mei = within(agents).getByText('MEI - Tan Mei Ling').closest('li')!;
    expect(within(mei).getByText('Leader')).toBeTruthy();
    const ali = within(agents).getByText('ALI - Ali Hassan').closest('li')!;
    expect(within(ali).queryByText('Leader')).toBeNull();
  });

  it('says "No leader" in the header when none is picked', () => {
    render(<SalesTeamDetail id="north" />);
    expect(screen.getByText('No leader')).toBeTruthy();
  });

  it('edits the leader in place, limited to the team\'s agents, and a new pick joins the team', async () => {
    hooks.useSalesTeam.mockReturnValue({
      data: detail({ leader_sales_agent_id: 'mei', leader_label: 'MEI - Tan Mei Ling' }),
      isLoading: false,
      isError: false,
    });
    render(<SalesTeamDetail id="north" />);
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));

    const leader = screen.getByLabelText('Leader') as HTMLSelectElement;
    expect(leader.value).toBe('mei');
    expect(leader.dataset.clearable).toBe('true');
    // The current agents only: not Kim, who left, and nobody outside the team.
    expect(Array.from(leader.options).map((o) => o.value)).toEqual(['', 'ali', 'mei']);

    fireEvent.click(screen.getByLabelText('RAJ - Raj Kumar (no team)'));
    expect(Array.from(leader.options).map((o) => o.value)).toEqual(['', 'ali', 'mei', 'raj']);
    fireEvent.change(leader, { target: { value: 'raj' } });

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(save.mutateAsync).toHaveBeenCalledTimes(1));
    expect(save.mutateAsync.mock.calls[0][0]).toMatchObject({
      sales_agent_ids: ['ali', 'mei', 'raj'],
      leader_sales_agent_id: 'raj',
    });
  });

  it('removing the leader in edit clears the leader', async () => {
    hooks.useSalesTeam.mockReturnValue({
      data: detail({ leader_sales_agent_id: 'mei', leader_label: 'MEI - Tan Mei Ling' }),
      isLoading: false,
      isError: false,
    });
    render(<SalesTeamDetail id="north" />);
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    fireEvent.click(screen.getByRole('button', { name: 'Remove MEI - Tan Mei Ling' }));
    expect((screen.getByLabelText('Leader') as HTMLSelectElement).value).toBe('');

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(save.mutateAsync).toHaveBeenCalledTimes(1));
    expect(save.mutateAsync.mock.calls[0][0].leader_sales_agent_id).toBeNull();
  });

  it('offers no Edit to a role without sales.teams.edit', () => {
    perms.granted = new Set(['sales.teams.view']);
    render(<SalesTeamDetail id="north" />);
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
    expect(screen.queryByRole('button', { name: /add agents/i })).toBeNull();
  });
});
