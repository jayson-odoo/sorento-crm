import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export interface UsageSummary {
  total_messages: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface UsageByDayItem {
  date: string;
  messages: number;
  tokens: number;
}

export interface TopUserItem {
  user_id: string;
  name: string;
  messages: number;
  tokens: number;
}

export interface TopContactItem {
  contact_id: string;
  name: string | null;
  phone_number: string | null;
  messages: number;
  tokens: number;
}

export type AIUsageFeature = 'ai_assistant' | 'ai_extract';

export interface RecentQueryItem {
  message_id: string;
  user_name: string | null;
  contact_name?: string | null;
  contact_phone?: string | null;
  feature?: AIUsageFeature | string | null;
  form_key?: string | null;
  query_preview: string;
  response_time_ms: number;
  tokens: number;
  created_at: string;
}

export interface QueryDetailToolUsed {
  name: string;
  ok: boolean;
}

export interface QueryDetail extends RecentQueryItem {
  reply: string;
  tools_used: QueryDetailToolUsed[];
}

export interface WishlistCluster {
  id: string;
  representative_question: string;
  category: string | null;
  count: number;
  last_seen_at: string;
  created_at: string;
}

async function unwrap<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) throw new Error(await extractApiError(res, fallback));
  return res.json() as Promise<T>;
}

function buildRange(
  from?: Date,
  to?: Date,
  extra?: Record<string, string | number | undefined>,
): string {
  const params = new URLSearchParams();
  if (from) params.set('from', from.toISOString());
  if (to) params.set('to', to.toISOString());
  if (extra) {
    for (const [k, v] of Object.entries(extra)) {
      if (v === undefined || v === null || v === '') continue;
      params.set(k, String(v));
    }
  }
  const s = params.toString();
  return s ? `?${s}` : '';
}

export async function getUsageSummary(
  from?: Date,
  to?: Date,
  feature?: string,
): Promise<UsageSummary> {
  const res = await apiFetch(
    `/api/v1/system/ai-assistant/usage/summary${buildRange(from, to, { feature })}`,
  );
  return unwrap(res, 'Failed to load usage summary.');
}

export async function getUsageByDay(
  from?: Date,
  to?: Date,
  feature?: string,
): Promise<UsageByDayItem[]> {
  const res = await apiFetch(
    `/api/v1/system/ai-assistant/usage/by-day${buildRange(from, to, { feature })}`,
  );
  return unwrap(res, 'Failed to load usage by-day.');
}

export async function getTopUsers(
  from?: Date,
  to?: Date,
  limit = 10,
  feature?: string,
): Promise<TopUserItem[]> {
  const res = await apiFetch(
    `/api/v1/system/ai-assistant/usage/top-users${buildRange(from, to, { limit, feature })}`,
  );
  return unwrap(res, 'Failed to load top users.');
}

export async function getTopContacts(
  from?: Date,
  to?: Date,
  limit = 10,
  feature: string = 'ai_extract',
): Promise<TopContactItem[]> {
  const res = await apiFetch(
    `/api/v1/system/ai-assistant/usage/top-contacts${buildRange(from, to, { limit, feature })}`,
  );
  return unwrap(res, 'Failed to load top contacts.');
}

export async function getRecentQueries(
  from?: Date,
  to?: Date,
  limit = 50,
  feature?: string,
): Promise<RecentQueryItem[]> {
  const res = await apiFetch(
    `/api/v1/system/ai-assistant/usage/recent-queries${buildRange(from, to, { limit, feature })}`,
  );
  return unwrap(res, 'Failed to load recent queries.');
}

export async function getQueryDetail(messageId: string): Promise<QueryDetail> {
  const res = await apiFetch(
    `/api/v1/system/ai-assistant/usage/queries/${encodeURIComponent(messageId)}`,
  );
  return unwrap(res, 'Failed to load query detail.');
}

export async function getWishlist(limit = 20): Promise<WishlistCluster[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  const res = await apiFetch(`/api/v1/system/ai-assistant/wishlist?${params.toString()}`);
  return unwrap(res, 'Failed to load wishlist.');
}
