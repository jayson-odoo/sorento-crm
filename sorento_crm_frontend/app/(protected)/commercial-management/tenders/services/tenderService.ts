import { apiFetch } from '@/lib/api';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

const base = '/api/v1/commercial/tenders';

export type TenderListRow = {
  tender_code: string;
  title: string;
  project_id: string;
  owner_name: string | null;
  forecast_amount: string | null;
  forecast_currency: string | null;
  pipeline_stage: string | null;
  expected_close_on: string | null;
  tender_lifecycle: string;
  tender_outcome: string;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type TenderDetail = TenderListRow & { outcome_notes: string | null };

export type TenderStageOption = {
  stage_code: string;
  stage_name: string;
  sort_order: number;
  is_terminal: boolean;
};

export type TenderSummary = {
  tender_code: string;
  title: string;
  tender_lifecycle: string;
  tender_outcome: string;
  pipeline_value_amount: string | null;
  pipeline_value_currency: string | null;
  in_open_pipeline: boolean;
  milestone_total: number;
  milestone_achieved: number;
  master_quotation_count: number;
  master_quotation_path_roles: Record<string, number>;
  master_quotation_stage_id_counts: Record<string, number>;
};

export type TenderMilestone = {
  id: string;
  tender_id: string;
  milestone_code: string;
  due_on: string | null;
  achieved_at: string | null;
  sort_order: number;
  created_at: string;
};

export type MasterQuotationRow = {
  id: string;
  quotation_code: string;
  title: string;
  path_role: string;
  quotation_stage_id: string;
  quoted_amount: string | null;
  quoted_currency: string | null;
};

export async function getTenders(
  params: DataGridApiFetchParams & { project_id?: string },
): Promise<DataGridApiResponse<TenderListRow>> {
  const { pageIndex, pageSize, project_id } = params;
  const q = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(project_id ? { project_id } : {}),
  });
  const res = await apiFetch(`${base}?${q.toString()}`);
  if (!res.ok) throw new Error('Failed to fetch tenders');
  return res.json();
}

export async function getTenderStagesSelect(): Promise<TenderStageOption[]> {
  const res = await apiFetch(`${base}/stages/select`);
  if (!res.ok) throw new Error('Failed to fetch tender stages');
  return res.json();
}

export async function getTenderByCode(tenderCode: string): Promise<TenderDetail> {
  const res = await apiFetch(`${base}/by-code/${encodeURIComponent(tenderCode)}`);
  if (!res.ok) throw new Error('Failed to fetch tender');
  return res.json();
}

export async function getTenderSummary(tenderCode: string): Promise<TenderSummary> {
  const res = await apiFetch(`${base}/by-code/${encodeURIComponent(tenderCode)}/summary`);
  if (!res.ok) throw new Error('Failed to fetch tender summary');
  return res.json();
}

export async function getTenderMilestones(tenderCode: string): Promise<TenderMilestone[]> {
  const res = await apiFetch(`${base}/by-code/${encodeURIComponent(tenderCode)}/milestones`);
  if (!res.ok) throw new Error('Failed to fetch milestones');
  return res.json();
}

export async function getTenderQuotations(tenderCode: string): Promise<MasterQuotationRow[]> {
  const res = await apiFetch(`${base}/by-code/${encodeURIComponent(tenderCode)}/quotations`);
  if (!res.ok) throw new Error('Failed to fetch quotations');
  return res.json();
}

export async function createTender(body: {
  project_id: string;
  tender_code: string;
  title: string;
  owner_user_id?: string | null;
  forecast_amount?: string | null;
  forecast_currency?: string | null;
  pipeline_stage?: string | null;
  expected_close_on?: string | null;
}): Promise<TenderDetail> {
  const res = await apiFetch(base, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to create tender');
  }
  return res.json();
}

export async function updateTender(
  tenderCode: string,
  body: Partial<{
    title: string;
    owner_user_id: string | null;
    forecast_amount: string | null;
    forecast_currency: string | null;
    pipeline_stage: string | null;
    expected_close_on: string | null;
  }>,
): Promise<TenderDetail> {
  const res = await apiFetch(`${base}/by-code/${encodeURIComponent(tenderCode)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to update tender');
  }
  return res.json();
}

export async function closeTender(
  tenderCode: string,
  body: { outcome: string; winning_master_quotation_id?: string | null; outcome_notes?: string | null },
): Promise<TenderDetail> {
  const res = await apiFetch(`${base}/by-code/${encodeURIComponent(tenderCode)}/close`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to close tender');
  }
  return res.json();
}

export async function reopenTender(tenderCode: string): Promise<TenderDetail> {
  const res = await apiFetch(`${base}/by-code/${encodeURIComponent(tenderCode)}/reopen`, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to reopen tender');
  }
  return res.json();
}

export async function createMilestone(
  tenderCode: string,
  body: { milestone_code: string; due_on?: string | null; sort_order?: number },
): Promise<TenderMilestone> {
  const res = await apiFetch(`${base}/by-code/${encodeURIComponent(tenderCode)}/milestones`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to create milestone');
  }
  return res.json();
}
