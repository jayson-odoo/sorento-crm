import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { LeaderboardRow } from '@/services/salesLeaderboardService';
import { LeaderboardPodium } from './LeaderboardPodium';

const row = (rank: number, person: string, amount: number, change: number | null = 10): LeaderboardRow => ({
  rank, name: person, keys: [], person, codes: [person], amount, qty: 0, prev_amount: 1, change_pct: change, customers: 1, products: 0, is_me: false,
});

const ROWS = [row(1, 'LCL', 1856856.61, 63.6), row(2, 'SEAN', 1276644.96, -10.4), row(3, 'JUSTIN', 1156644.97, null)];

function order() {
  return [...screen.getByTestId('leaderboard-podium').children].map((el) => el.getAttribute('data-testid'));
}

describe('LeaderboardPodium', () => {
  it('puts #1 in the middle of three cards', () => {
    render(<LeaderboardPodium rows={ROWS} versus="Sep" />);
    expect(order()).toEqual(['leaderboard-podium-2', 'leaderboard-podium-1', 'leaderboard-podium-3']);
  });

  it('shows each person with RM and the change, a dash when there is none', () => {
    render(<LeaderboardPodium rows={ROWS} versus="Sep" />);
    expect(screen.getByText('RM 1,856,856.61')).toBeTruthy();
    expect(screen.getByText('+63.6% vs Sep')).toBeTruthy();
    expect(screen.getByText('-10.4% vs Sep')).toBeTruthy();
    expect(screen.getAllByText('-').length).toBeGreaterThan(0);
  });

  it('shows only the cards it has for two rows and for one', () => {
    const { unmount } = render(<LeaderboardPodium rows={ROWS.slice(0, 2)} versus="Sep" />);
    expect(order()).toEqual(['leaderboard-podium-1', 'leaderboard-podium-2']);
    unmount();
    render(<LeaderboardPodium rows={ROWS.slice(0, 1)} versus="Sep" />);
    expect(order()).toEqual(['leaderboard-podium-1']);
  });

  it('renders nothing without rows', () => {
    const { container } = render(<LeaderboardPodium rows={[]} versus="Sep" />);
    expect(container.firstChild).toBeNull();
  });

  it('leaves the codes line out when the single code is the name', () => {
    render(<LeaderboardPodium rows={[{ ...row(1, 'LCL', 100), codes: ['LCL'] }]} versus="Sep" />);
    expect(screen.getByTestId('leaderboard-podium-1').querySelectorAll('span[title]').length).toBe(1); // the name only
  });

  it('shows the codes line for several codes', () => {
    render(<LeaderboardPodium rows={[{ ...row(1, 'SEAN', 100), codes: ['SEAN I', 'SEAN III'] }]} versus="Sep" />);
    expect(screen.getByTitle('SEAN I, SEAN III')).toBeTruthy();
  });
});
