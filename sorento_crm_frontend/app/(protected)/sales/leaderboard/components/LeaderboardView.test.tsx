import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import type { LeaderboardResponse, LeaderboardRow } from '@/services/salesLeaderboardService';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;

vi.mock('next/navigation', () => ({
  usePathname: () => '/sales/leaderboard',
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
  PageHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
}));

const state = vi.hoisted(() => ({ data: undefined as unknown, calls: [] as unknown[], isError: false, isFetching: false, isLoading: false }));
vi.mock('@/hooks/useSalesLeaderboardQuery', () => ({
  useSalesLeaderboardQuery: (params: unknown) => {
    state.calls.push(params);
    return {
      data: state.data,
      isLoading: state.isLoading,
      isFetching: state.isFetching,
      isError: state.isError,
      error: state.isError ? new Error('Failed to load the leaderboard') : null,
    };
  },
  useSalesLeaderboardOptionsQuery: () => ({ data: { companies: [], brands: [], categories: [] } }),
}));

import LeaderboardView from './LeaderboardView';

const row = (rank: number, person: string, amount: number, is_me = false): LeaderboardRow => ({
  rank, name: person, keys: [], person, codes: [person], amount, qty: 0, prev_amount: 100, change_pct: 27.6, customers: 3, products: 0, is_me,
});

function response(rows: LeaderboardRow[], me: LeaderboardResponse['me']): LeaderboardResponse {
  return {
    basis: 'invoiced', by: 'person', can_drill_others: true,
    date_from: '2026-10-01', date_to: '2026-10-31', previous_from: '2026-09-01', previous_to: '2026-09-30',
    as_of: '2026-11-04T03:10:00',
    total: { amount: 16369803.26, qty: 0, prev_amount: 15894544.36, change_pct: 3.0, customers: 0, products: 0 },
    no_agent_amount: 1210.32, rows, me,
  };
}

beforeEach(() => {
  state.calls = [];
  state.isError = false;
  state.isFetching = false;
  state.isLoading = false;
});

describe('LeaderboardView', () => {
  it('highlights the signed-in user\'s row and shows the Your rank tile', () => {
    state.data = response(
      [row(1, 'LCL', 900), row(2, 'SEAN', 800), row(3, 'JUSTIN', 700), row(4, 'JENNIFER', 600, true)],
      { person: 'JENNIFER', rank: 4 },
    );
    const { container } = render(<LeaderboardView />);
    expect(container.querySelectorAll('tr[data-me="true"]').length).toBe(1);
    expect(screen.getByText('Your rank')).toBeTruthy();
    expect(screen.getByText('#4')).toBeTruthy();
    expect(within(screen.getByTestId('leaderboard-kpis')).getByText('RM 16,369,803.26')).toBeTruthy();
  });

  it('omits the Your rank tile when the user is not linked to an agent', () => {
    state.data = response([row(1, 'LCL', 900)], null);
    const { container } = render(<LeaderboardView />);
    expect(screen.queryByText('Your rank')).toBeNull();
    expect(container.querySelectorAll('tr[data-me="true"]').length).toBe(0);
  });

  it('shows the no-agent footer and the data-as-of line', () => {
    state.data = response([row(1, 'LCL', 900)], null);
    render(<LeaderboardView />);
    expect(screen.getByTestId('leaderboard-no-agent').textContent).toBe(
      'Sales with no agent: RM 1,210.32 (not ranked)',
    );
    expect(screen.getByTestId('leaderboard-as-of').textContent).toContain('04/11/2026');
  });

  it('shows the empty state with a heading and a hint, and no podium or grid', () => {
    state.data = response([], null);
    render(<LeaderboardView />);
    const empty = screen.getByTestId('leaderboard-empty');
    expect(within(empty).getByText('No sales in this period')).toBeTruthy();
    expect(within(empty).queryByRole('button')).toBeNull();
    expect(screen.queryByTestId('leaderboard-podium')).toBeNull();
  });

  it('shows the error and no empty-state heading when the read failed', () => {
    state.data = undefined;
    state.isError = true;
    render(<LeaderboardView />);
    expect(screen.getByText('Failed to load the leaderboard')).toBeTruthy();
    expect(screen.queryByTestId('leaderboard-empty')).toBeNull();
    expect(screen.queryByText('No sales in this period')).toBeNull();
  });

  it('dims the old board and shows Updating board while a new period is fetching behind it', () => {
    state.data = response([row(1, 'LCL', 900)], null);
    state.isFetching = true;
    render(<LeaderboardView />);
    const board = screen.getByTestId('leaderboard-board');
    expect(board.getAttribute('aria-busy')).toBe('true');
    expect(board.className).toContain('opacity-50');
    expect(screen.getByTestId('leaderboard-loading').textContent).toContain('Updating board');
  });

  it('is not dimmed and shows no Loading when idle', () => {
    state.data = response([row(1, 'LCL', 900)], null);
    render(<LeaderboardView />);
    expect(screen.getByTestId('leaderboard-board').getAttribute('aria-busy')).toBe('false');
    expect(screen.queryByTestId('leaderboard-loading')).toBeNull();
  });

  it('shows skeletons on the first load, with no board and no empty state', () => {
    state.data = undefined;
    state.isLoading = true;
    state.isFetching = true;
    render(<LeaderboardView />);
    expect(screen.getByTestId('leaderboard-skeleton')).toBeTruthy();
    expect(screen.queryByTestId('leaderboard-empty')).toBeNull();
  });

  it('shows Pick a date range when Custom has no range yet', () => {
    state.data = undefined;
    render(<LeaderboardView />);
    fireEvent.click(screen.getByRole('button', { name: 'Custom' }));
    const hint = screen.getByTestId('leaderboard-pick-range');
    expect(within(hint).getByText('Pick a date range')).toBeTruthy();
    expect(within(hint).queryByRole('button')).toBeNull();
    expect(screen.queryByTestId('leaderboard-empty')).toBeNull();
  });

  it('repeats no code under a name: blank for a single code equal to the person, shown otherwise', () => {
    state.data = response(
      [
        { ...row(1, 'LCL', 900), codes: ['LCL'] },
        { ...row(2, 'SEAN', 800), codes: ['SEAN I', 'SEAN III'] },
        { ...row(3, 'JUSTIN', 700), codes: ['JUSTIN'] },
        { ...row(4, 'JIMMY', 600), codes: ['JIM-1'] },
      ],
      null,
    );
    const { container } = render(<LeaderboardView />);
    const cells = [...container.querySelectorAll('td span[title]')].map((el) => el.getAttribute('title'));
    expect(cells).not.toContain('LCL, LCL');
    expect(container.querySelector('td span[title="SEAN I, SEAN III"]')).toBeTruthy();
    expect(container.querySelector('td span[title="JIM-1"]')).toBeTruthy();
    expect(screen.queryAllByText('Codes').length).toBeGreaterThan(0);
  });

  it('hides the whole Codes column when no row has codes to show', () => {
    state.data = response(
      [
        { ...row(1, 'LCL', 900), codes: ['LCL'] },
        { ...row(2, 'JUSTIN', 700), codes: ['JUSTIN'] },
      ],
      null,
    );
    render(<LeaderboardView />);
    expect(screen.queryByText('Codes')).toBeNull();
    expect(screen.getAllByText('Sales person').length).toBeGreaterThan(0);
  });

  it('asks for This month with its previous window by default', () => {
    state.data = response([], null);
    render(<LeaderboardView />);
    const params = state.calls[0] as Record<string, string>;
    expect(params.date_from).toMatch(/^\d{4}-\d{2}-01$/);
    expect(params.previous_from).toMatch(/^\d{4}-\d{2}-01$/);
    expect(params.previous_to).toBeTruthy();
  });
});
