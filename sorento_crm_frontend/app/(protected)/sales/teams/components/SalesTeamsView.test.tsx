/**
 * Sales > Sales Teams (UAC S6-9, S6-12; owner ruling 26 Sep 06:01 (Lavish), N2 and N4).
 *
 * Modelled on Users & Access > Teams: a PageHeader with Add team as its one primary action, a
 * search box, and a DataGrid with one line per team (name, agents as pills with "+N", Active
 * badge). Empty state "No sales teams yet" with Add team.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;

vi.mock('next/navigation', () => ({
  usePathname: () => '/sales/teams',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/common/PageHeader', () => ({
  PageHeader: ({ title, actions }: { title: string; actions?: React.ReactNode }) => (
    <header>
      <h1>{title}</h1>
      <div data-testid="header-actions">{actions}</div>
    </header>
  ),
}));

const perms = vi.hoisted(() => ({ granted: new Set<string>() }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => perms.granted.has(slug),
}));

const hooks = vi.hoisted(() => ({ useSalesTeams: vi.fn() }));
vi.mock('../hooks/useSalesTeams', () => hooks);

vi.mock('./SalesTeamModal', () => ({
  default: ({ open }: { open: boolean }) => (open ? <div role="dialog">team modal</div> : null),
}));
vi.mock('../actions', () => ({
  SalesTeamRowActions: () => <button type="button">row actions</button>,
}));

import SalesTeamsView from './SalesTeamsView';
import type { SalesTeamListItem } from '../types/salesTeam.types';

function team(over: Partial<SalesTeamListItem> = {}): SalesTeamListItem {
  return {
    id: 'north',
    name: 'North',
    is_active: true,
    leader_sales_agent_id: null,
    member_count: 2,
    members: [
      { sales_agent_id: 'ali', label: 'ALI - Ali Hassan' },
      { sales_agent_id: 'mei', label: 'MEI - Tan Mei Ling' },
    ],
    created_at: '2026-09-26T01:00:00',
    updated_at: '2026-09-26T01:00:00',
    ...over,
  };
}

function withTeams(data: SalesTeamListItem[]) {
  hooks.useSalesTeams.mockReturnValue({
    data: { data, pagination: { total: data.length, page: 1, limit: 50 }, empty: data.length === 0 },
    isLoading: false,
    isFetching: false,
    isError: false,
    refetch: vi.fn(),
  });
}

beforeEach(() => {
  perms.granted = new Set(['sales.teams.view', 'sales.teams.add', 'sales.teams.delete']);
  hooks.useSalesTeams.mockReset();
});

describe('SalesTeamsView', () => {
  it('titles the page "Sales teams" with Add team as the header action', () => {
    withTeams([team()]);
    render(<SalesTeamsView />);
    expect(screen.getByRole('heading', { name: 'Sales teams' })).toBeTruthy();
    const actions = screen.getByTestId('header-actions');
    fireEvent.click(within(actions).getByRole('button', { name: /add team/i }));
    expect(screen.getByRole('dialog')).toBeTruthy();
  });

  it('draws one line per team: name, agent pills and the Active badge', () => {
    withTeams([
      team(),
      team({ id: 'central', name: 'Central', is_active: false, member_count: 0, members: [] }),
    ]);
    render(<SalesTeamsView />);
    const north = screen.getByText('North').closest('tr')!;
    expect(within(north).getAllByText('ALI - Ali Hassan').length).toBeGreaterThan(0);
    expect(within(north).getByText('Active')).toBeTruthy();
    const central = screen.getByText('Central').closest('tr')!;
    expect(within(central).getByText('Inactive')).toBeTruthy();
    expect(within(central).getByText('No agents')).toBeTruthy();
  });

  it('marks the leader\'s pill with a Leader tag and draws it first (W1)', () => {
    withTeams([team({ leader_sales_agent_id: 'mei' })]);
    render(<SalesTeamsView />);
    const north = screen.getByText('North').closest('tr')!;
    const pills = within(north).getAllByRole('button').filter((b) => b.textContent?.includes(' - '));
    expect(pills[0].textContent).toBe('MEI - Tan Mei Ling (Leader)');
    expect(within(north).queryByText('ALI - Ali Hassan (Leader)')).toBeNull();
  });

  it('tags no pill when the team has no leader', () => {
    withTeams([team()]);
    render(<SalesTeamsView />);
    const north = screen.getByText('North').closest('tr')!;
    expect(within(north).queryAllByText(/\(Leader\)/).length).toBe(0);
  });

  it('shows "No sales teams yet" with Add team when there are none', () => {
    withTeams([]);
    render(<SalesTeamsView />);
    expect(screen.getByText('No sales teams yet')).toBeTruthy();
    const cta = screen.getAllByRole('button', { name: /add team/i });
    expect(cta.length).toBe(2);
    fireEvent.click(cta[1]);
    expect(screen.getByRole('dialog')).toBeTruthy();
  });

  it('offers no Add team to a role without sales.teams.add', () => {
    perms.granted = new Set(['sales.teams.view']);
    withTeams([]);
    render(<SalesTeamsView />);
    expect(screen.queryByRole('button', { name: /add team/i })).toBeNull();
  });

  it('searches by name through the hook', () => {
    withTeams([team()]);
    render(<SalesTeamsView />);
    expect(hooks.useSalesTeams).toHaveBeenCalledWith('');
  });
});
