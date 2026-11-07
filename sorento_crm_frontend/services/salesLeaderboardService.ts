/**
 * salesLeaderboardService: the contract with /api/v1/sales/leaderboard (PLAN-sales-leaderboard-07nov,
 * "Contract"). Layering: components -> hooks (useSalesLeaderboardQuery) -> THIS service -> lib/api.
 *
 *   GET /sales/leaderboard?basis&by&date_from&date_to&previous_from&previous_to&company&brand&category
 *       &channel&person&customer&product                              -> LeaderboardResponse
 *   (SALES-INSIGHTS-P2, plan "Contract"; the dates are absent on Undelivered "All open")
 *   GET /sales/leaderboard/options                                   -> LeaderboardOptions
 * Both gated on `sales.leaderboard.view`. `brand`, `category`, `channel`, `person`, `customer` and `product` repeat per value.
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export type LeaderboardBasis = 'invoiced' | 'delivered' | 'ordered' | 'outstanding';
export type LeaderboardBy = 'person' | 'customer' | 'product' | 'brand' | 'category' | 'channel';

export interface LeaderboardTarget {
  target_no: string;
  basis: string;
  period_from: string;
  period_to: string;
  target_amount: number;
  achieved_amount: number;
  achieved_pct: number | null;
  like_for_like: boolean;
}

export interface LeaderboardTotal {
  amount: number;
  qty: number;
  /** null on Undelivered (no compare there). */
  prev_amount: number | null;
  /** null when prev_amount <= 0. */
  change_pct: number | null;
  customers: number;
  products: number;
}

/** One ranked row. The view-specific fields are present only on that view. */
export interface LeaderboardRow {
  rank: number;
  name: string;
  /** The ids the name stands for (customer / product / brand / category); [] for a person and a blank row. */
  keys: string[];
  amount: number;
  qty: number;
  prev_amount: number | null;
  change_pct: number | null;
  customers: number;
  products: number;
  // by person
  person?: string;
  codes?: string[];
  is_me?: boolean;
  target?: LeaderboardTarget | null;
  // by customer
  code?: string;
  companies?: string[];
  // by product
  brand?: string | null;
  category?: string | null;
  // by channel
  key?: string | null;
}

export interface LeaderboardResponse {
  basis: LeaderboardBasis;
  by: LeaderboardBy;
  /** null on Undelivered "All open". */
  date_from: string | null;
  date_to: string | null;
  previous_from: string | null;
  previous_to: string | null;
  /** Naive UTC datetime, null when no document was ever synced. */
  as_of: string | null;
  total: LeaderboardTotal;
  no_agent_amount: number;
  rows: LeaderboardRow[];
  me: { person: string; rank: number } | null;
  can_drill_others: boolean;
}

export interface LeaderboardOption {
  value: string;
  label: string;
}

export interface LeaderboardOptions {
  companies: LeaderboardOption[];
  brands: LeaderboardOption[];
  categories: LeaderboardOption[];
  channels: Record<LeaderboardBasis, LeaderboardOption[]>;
  can: Record<LeaderboardBasis, boolean>;
}

export interface LeaderboardParams {
  basis?: LeaderboardBasis;
  by?: LeaderboardBy;
  /** Absent on Undelivered "All open". */
  date_from?: string;
  date_to?: string;
  /** Both or neither; absent = the same number of days just before. */
  previous_from?: string;
  previous_to?: string;
  company?: string;
  brand?: string[];
  category?: string[];
  channel?: string[];
  /** Drill filters: person labels, customer ids, product ids. */
  person?: string[];
  customer?: string[];
  product?: string[];
}

const BASE = '/api/v1/sales/leaderboard';

function query(params: LeaderboardParams): string {
  const search = new URLSearchParams();
  if (params.basis) search.set('basis', params.basis);
  if (params.by) search.set('by', params.by);
  if (params.date_from) search.set('date_from', params.date_from);
  if (params.date_to) search.set('date_to', params.date_to);
  if (params.previous_from && params.previous_to) {
    search.set('previous_from', params.previous_from);
    search.set('previous_to', params.previous_to);
  }
  if (params.company) search.set('company', params.company);
  for (const id of params.brand ?? []) search.append('brand', id);
  for (const id of params.category ?? []) search.append('category', id);
  for (const value of params.channel ?? []) search.append('channel', value);
  for (const label of params.person ?? []) search.append('person', label);
  for (const id of params.customer ?? []) search.append('customer', id);
  for (const id of params.product ?? []) search.append('product', id);
  return search.toString();
}

export async function getLeaderboard(params: LeaderboardParams): Promise<LeaderboardResponse> {
  const response = await apiFetch(`${BASE}?${query(params)}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load the leaderboard'));
  return response.json();
}

export async function getLeaderboardOptions(): Promise<LeaderboardOptions> {
  const response = await apiFetch(`${BASE}/options`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load the filters'));
  return response.json();
}
