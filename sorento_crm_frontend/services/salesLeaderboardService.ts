/**
 * salesLeaderboardService: the contract with /api/v1/sales/leaderboard (PLAN-sales-leaderboard-07nov,
 * "Contract"). Layering: components -> hooks (useSalesLeaderboardQuery) -> THIS service -> lib/api.
 *
 *   GET /sales/leaderboard?date_from&date_to&company&brand&category  -> LeaderboardResponse
 *   GET /sales/leaderboard/options                                   -> LeaderboardOptions
 * Both gated on `sales.leaderboard.view`. `brand` and `category` repeat per id.
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import { MOCK_LEADERBOARD, MOCK_LEADERBOARD_OPTIONS } from './salesLeaderboardMock';

/** Phase 1: serve the mock. The captain flips this to false when the backend lands. */
const USE_MOCK = true;

export interface LeaderboardTotal {
  amount: number;
  prev_amount: number;
  /** null when prev_amount <= 0. */
  change_pct: number | null;
}

export interface LeaderboardRow {
  rank: number;
  person: string;
  codes: string[];
  amount: number;
  prev_amount: number;
  change_pct: number | null;
  customers: number;
  is_me: boolean;
}

export interface LeaderboardResponse {
  date_from: string;
  date_to: string;
  previous_from: string;
  previous_to: string;
  /** Naive UTC datetime, null when no document was ever synced. */
  as_of: string | null;
  total: LeaderboardTotal;
  no_agent_amount: number;
  rows: LeaderboardRow[];
  me: { person: string; rank: number } | null;
}

export interface LeaderboardOption {
  value: string;
  label: string;
}

export interface LeaderboardOptions {
  companies: LeaderboardOption[];
  brands: LeaderboardOption[];
  categories: LeaderboardOption[];
}

export interface LeaderboardParams {
  date_from: string;
  date_to: string;
  company?: string;
  brand?: string[];
  category?: string[];
}

const BASE = '/api/v1/sales/leaderboard';

function query(params: LeaderboardParams): string {
  const search = new URLSearchParams({ date_from: params.date_from, date_to: params.date_to });
  if (params.company) search.set('company', params.company);
  for (const id of params.brand ?? []) search.append('brand', id);
  for (const id of params.category ?? []) search.append('category', id);
  return search.toString();
}

export async function getLeaderboard(params: LeaderboardParams): Promise<LeaderboardResponse> {
  if (USE_MOCK) return MOCK_LEADERBOARD;
  const response = await apiFetch(`${BASE}?${query(params)}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load the leaderboard'));
  return response.json();
}

export async function getLeaderboardOptions(): Promise<LeaderboardOptions> {
  if (USE_MOCK) return MOCK_LEADERBOARD_OPTIONS;
  const response = await apiFetch(`${BASE}/options`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load the filters'));
  return response.json();
}
