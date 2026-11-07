/**
 * MOCK data for the sales leaderboard (Phase 1, PLAN-sales-leaderboard-07nov). Real October 2026
 * figures from the dev copy; ranks 11-19 are plausible fill-ins, not real. Delete with the
 * `USE_MOCK` flag in salesLeaderboardService.ts when the backend lands.
 */
import type { LeaderboardOptions, LeaderboardResponse, LeaderboardRow } from './salesLeaderboardService';

type Seed = [number, string, string[], number, number, number | null, number, boolean?];

const SEEDS: Seed[] = [
  [1, 'LCL', ['LCL'], 1856856.61, 1135260.82, 63.6, 24],
  [2, 'SEAN', ['SEAN I', 'SEAN III', 'SEAN IV'], 1276644.96, 1424174.94, -10.4, 90],
  [3, 'JUSTIN', ['JUSTIN'], 1156644.97, 710262.35, 62.8, 20],
  [4, 'JIMMY', ['JIMMY - I', 'JIMMY - II', 'JIMMY - III'], 1094512.87, 879992.17, 24.4, 70],
  [5, 'LONG', ['LONG I', 'LONG III', 'LONG IV'], 982956.94, 839467.12, 17.1, 50],
  [6, 'FANNY', ['FANNY I', 'FANNY III', 'FANNY IV'], 949878.0, 1289228.58, -26.3, 25],
  [7, 'ERIC NG', ['ERIC NG'], 805048.34, 966119.17, -16.7, 16],
  [8, 'WT', ['WT I', 'WT III', 'WT IV'], 684012.74, 679953.05, 0.6, 52],
  [9, 'ACT', ['ACT'], 627020.93, 819508.32, -23.5, 15],
  [10, 'KENT', ['KENT - I', 'KENT - II', 'KENT - III'], 594403.18, 511756.14, 16.1, 38],
  [11, 'ALVIN', ['ALVIN'], 561200.4, 498310.2, 12.6, 21],
  [12, 'BENNY', ['BENNY I', 'BENNY II'], 534870.15, 601442.9, -11.1, 33],
  [13, 'CHONG', ['CHONG'], 498112.0, 402991.6, 23.6, 19],
  [14, 'DAVID', ['DAVID'], 455390.77, 455390.77, 0.0, 17],
  [15, 'EDDIE', ['EDDIE I', 'EDDIE II'], 421005.3, 380220.45, 10.7, 29],
  [16, 'GARY', ['GARY'], 388764.12, 512880.0, -24.2, 14],
  [17, 'HENRY', ['HENRY'], 351209.9, 0, null, 12],
  [18, 'IVAN', ['IVAN I', 'IVAN III'], 322870.55, 301115.2, 7.2, 22],
  [19, 'KELVIN', ['KELVIN'], 305998.0, 340775.3, -10.2, 18],
  [20, 'JENNIFER', ['JENNIFER'], 291522.87, 228388.15, 27.6, 28, true],
];

const rows: LeaderboardRow[] = SEEDS.map(
  ([rank, person, codes, amount, prev_amount, change_pct, customers, is_me]) => ({
    rank,
    person,
    codes,
    amount,
    prev_amount,
    change_pct,
    customers,
    is_me: Boolean(is_me),
  }),
);

export const MOCK_LEADERBOARD: LeaderboardResponse = {
  date_from: '2026-10-01',
  date_to: '2026-10-31',
  previous_from: '2026-09-01',
  previous_to: '2026-09-30',
  as_of: '2026-11-04T03:10:00',
  total: { amount: 16369803.26, prev_amount: 15894544.36, change_pct: 3.0 },
  no_agent_amount: 1210.32,
  rows,
  me: { person: 'JENNIFER', rank: 20 },
};

export const MOCK_LEADERBOARD_OPTIONS: LeaderboardOptions = {
  companies: [
    { value: 'mock-company-srt', label: 'SRT' },
    { value: 'mock-company-mch', label: 'MCH' },
  ],
  brands: [
    { value: 'mock-brand-1', label: 'Sorento' },
    { value: 'mock-brand-2', label: 'Nordic' },
    { value: 'mock-brand-3', label: 'Aqua' },
  ],
  categories: [
    { value: 'mock-cat-1', label: 'Tiles' },
    { value: 'mock-cat-2', label: 'Sanitary ware' },
    { value: 'mock-cat-3', label: 'Fittings' },
  ],
};
