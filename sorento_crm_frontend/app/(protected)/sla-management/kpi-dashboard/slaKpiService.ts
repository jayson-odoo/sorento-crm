import { apiFetch } from '@/lib/api';

export type KpiScope = 'all' | 'conversation' | 'form';

export interface KpiSummary {
  scope: string;
  opened: number;
  responded: number;
  resolved: number;
  escalated: number;
  escalated_auto: number;
  escalated_manual: number;
  response_met: number;
  response_breach: number;
  resolution_met: number;
  resolution_breach: number;
  pct_response_met: number | null;
  pct_resolution_met: number | null;
  avg_response_time_hours: number | null;
  avg_resolution_time_hours: number | null;
  median_response_time_hours: number | null;
  median_resolution_time_hours: number | null;
}

export interface KpiLeaderRow {
  assignee_id: string;
  assignee_name: string;
  total: number;
  resolved: number;
  avg_response_time_hours: number | null;
  avg_resolution_time_hours: number | null;
  breach_count: number;
}

export interface KpiTaskRow {
  tracking_id: string;
  source_entity_type: string | null;
  source_entity_id: string | null;
  current_tier: number;
  assignee_id: string | null;
  assignee_name: string;
  response_time_hours: number | null;
  resolution_time_hours: number | null;
  is_resolved: boolean;
  response_met: boolean;
  resolution_met: boolean;
  escalations_auto: number;
  escalations_manual: number;
}

const BASE = '/api/v1/sla-management/kpi';

function qs(scope: KpiScope, extra: Record<string, string | number> = {}) {
  const sp = new URLSearchParams({ scope });
  for (const [k, v] of Object.entries(extra)) sp.set(k, String(v));
  return sp.toString();
}

export async function getKpiSummary(scope: KpiScope): Promise<KpiSummary> {
  const r = await apiFetch(`${BASE}/summary?${qs(scope)}`);
  if (!r.ok) throw new Error('Failed to load KPI summary');
  return r.json();
}

export async function getKpiLeaderboard(scope: KpiScope): Promise<KpiLeaderRow[]> {
  const r = await apiFetch(`${BASE}/leaderboard?${qs(scope)}`);
  if (!r.ok) throw new Error('Failed to load leaderboard');
  return (await r.json()).data ?? [];
}

export async function getKpiTasks(
  scope: KpiScope,
  page = 1,
  limit = 25,
): Promise<{ data: KpiTaskRow[]; total: number }> {
  const r = await apiFetch(`${BASE}/tasks?${qs(scope, { page, limit })}`);
  if (!r.ok) throw new Error('Failed to load tasks');
  return r.json();
}
