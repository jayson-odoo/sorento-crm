import { apiFetch } from '@/lib/api';
import { buildDataGridParams } from '@/lib/api-client';
import type { PaginationState, SortingState } from '@tanstack/react-table';

export type KpiScope = 'all' | 'conversation' | 'form';
export type KpiView = 'all' | 'responded' | 'resolved' | 'pending' | 'responded_open';
export type KpiState = 'all' | 'within' | 'overdue';
// "Escalating by when" filter on the tasks list. overdue = escalation clock
// already past; Nh = next escalation fires within N hours.
export type KpiEscWindow = 'all' | 'overdue' | '1h' | '4h' | '24h';

// Optional inclusive date window (ISO `YYYY-MM-DD`). When omitted the backend
// aggregates over all time. The home-dashboard embed passes a bounded window;
// the dedicated route leaves it unset.
export interface KpiWindow {
  date_from?: string;
  date_to?: string;
}

function windowExtra(window?: KpiWindow): Record<string, string> {
  const extra: Record<string, string> = {};
  if (window?.date_from) extra.date_from = window.date_from;
  if (window?.date_to) extra.date_to = window.date_to;
  return extra;
}

export interface KpiSummary {
  scope: string;
  opened: number;
  responded: number;
  resolved: number;
  stage_pending: number;
  stage_responded_open: number;
  stage_resolved: number;
  pct_stage_pending: number | null;
  pct_stage_responded_open: number | null;
  pct_stage_resolved: number | null;
  responded_within: number;
  responded_overdue: number;
  resolved_within: number;
  resolved_overdue: number;
  pct_responded_within: number | null;
  pct_resolved_within: number | null;
  pending_within: number;
  pending_overdue: number;
  responded_open_within: number;
  responded_open_overdue: number;
  pct_pending_within: number | null;
  pct_responded_open_within: number | null;
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
  current_tier_started_at: string | null;
  response_due: string | null;
  resolution_due: string | null;
  escalates_at: string | null;
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

export interface KpiTrendPoint {
  bucket: string;
  opened: number;
  resolved: number;
}

const BASE = '/api/v1/sla-management/kpi';

function qs(scope: KpiScope, extra: Record<string, string | number> = {}) {
  const sp = new URLSearchParams({ scope });
  for (const [k, v] of Object.entries(extra)) sp.set(k, String(v));
  return sp.toString();
}

export async function getKpiSummary(scope: KpiScope, window?: KpiWindow): Promise<KpiSummary> {
  const r = await apiFetch(`${BASE}/summary?${qs(scope, windowExtra(window))}`);
  if (!r.ok) throw new Error('Failed to load KPI summary');
  return r.json();
}

export async function getKpiLeaderboard(scope: KpiScope): Promise<KpiLeaderRow[]> {
  const r = await apiFetch(`${BASE}/leaderboard?${qs(scope)}`);
  if (!r.ok) throw new Error('Failed to load leaderboard');
  return (await r.json()).data ?? [];
}

export async function getKpiTrend(scope: KpiScope, window?: KpiWindow): Promise<KpiTrendPoint[]> {
  const r = await apiFetch(`${BASE}/trend?${qs(scope, windowExtra(window))}`);
  if (!r.ok) throw new Error('Failed to load trend');
  return (await r.json()).data ?? [];
}

export async function getKpiTasks(
  scope: KpiScope,
  pagination: PaginationState,
  sorting: SortingState = [],
  view: KpiView = 'all',
  state: KpiState = 'all',
  window?: KpiWindow,
  escWindow: KpiEscWindow = 'all',
): Promise<{ data: KpiTaskRow[]; total: number }> {
  const params = buildDataGridParams(
    {
      pageIndex: pagination.pageIndex,
      pageSize: pagination.pageSize,
      sorting,
      searchQuery: '',
    },
    { scope, view, state, esc_window: escWindow, ...windowExtra(window) },
  );
  const r = await apiFetch(`${BASE}/tasks?${params.toString()}`);
  if (!r.ok) throw new Error('Failed to load tasks');
  return r.json();
}
