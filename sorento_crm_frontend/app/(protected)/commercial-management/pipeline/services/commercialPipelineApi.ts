import { apiFetch } from '@/lib/api';

export type ScopeParam = 'mine' | 'all';

export interface StageInfo {
  code: string;
  label: string;
  sort_order: number;
  is_terminal: boolean;
}

export interface StageConfig {
  lead_stages: StageInfo[];
  tender_stages: StageInfo[];
  mq_execution_states: StageInfo[];
  pipeline_task_statuses: StageInfo[];
  activity_task_statuses: StageInfo[];
}

export interface KanbanBoardPayload {
  columns: Record<string, Record<string, unknown>[]>;
  column_order: string[];
}

export async function fetchStageConfig(): Promise<StageConfig> {
  const res = await apiFetch('/api/commercial/pipeline/stage-config');
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchKanbanLeads(scope: ScopeParam, stage_code?: string): Promise<KanbanBoardPayload> {
  const q = new URLSearchParams({ scope });
  if (stage_code) q.set('stage_code', stage_code);
  const res = await apiFetch(`/api/commercial/pipeline/kanban/leads?${q}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchKanbanTenders(
  scope: ScopeParam,
  pipeline_stage?: string,
  tender_outcome?: string,
): Promise<KanbanBoardPayload> {
  const q = new URLSearchParams({ scope });
  if (pipeline_stage) q.set('pipeline_stage', pipeline_stage);
  if (tender_outcome) q.set('tender_outcome', tender_outcome);
  const res = await apiFetch(`/api/commercial/pipeline/kanban/tenders?${q}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchKanbanMasterQuotations(
  scope: ScopeParam,
  execution_state?: string,
): Promise<KanbanBoardPayload> {
  const q = new URLSearchParams({ scope });
  if (execution_state) q.set('execution_state', execution_state);
  const res = await apiFetch(`/api/commercial/pipeline/kanban/master-quotations?${q}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchKanbanTasks(
  scope: ScopeParam,
  opts?: { overdue_only?: boolean; due_soon_only?: boolean; include_activity?: boolean },
): Promise<KanbanBoardPayload> {
  const q = new URLSearchParams({ scope });
  if (opts?.overdue_only) q.set('overdue_only', 'true');
  if (opts?.due_soon_only) q.set('due_soon_only', 'true');
  if (opts?.include_activity === false) q.set('include_activity', 'false');
  const res = await apiFetch(`/api/commercial/pipeline/kanban/tasks?${q}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function patchLeadStage(lead_code: string, stage_code: string): Promise<void> {
  const res = await apiFetch(`/api/commercial/pipeline/kanban/leads/${encodeURIComponent(lead_code)}/stage`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ stage_code }),
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function patchTenderPipeline(tender_code: string, pipeline_stage: string | null): Promise<void> {
  const res = await apiFetch(`/api/commercial/pipeline/kanban/tenders/${encodeURIComponent(tender_code)}/pipeline`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pipeline_stage }),
  });
  if (!res.ok) throw new Error(await res.text());
}

export type PatchMqExecutionResult = {
  ok?: boolean;
  applied_stage_code?: string;
  rerouted_for_approval?: boolean;
};

export async function patchMqExecution(
  tender_code: string,
  quotation_code: string,
  execution_state: string,
): Promise<PatchMqExecutionResult> {
  const res = await apiFetch(
    `/api/commercial/pipeline/kanban/tenders/${encodeURIComponent(tender_code)}/master-quotations/${encodeURIComponent(quotation_code)}/execution`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ execution_state }),
    },
  );
  const raw = await res.text();
  if (!res.ok) {
    let msg = raw;
    try {
      const j = JSON.parse(raw) as { detail?: string };
      if (j.detail) msg = j.detail;
    } catch {
      /* use raw */
    }
    throw new Error(msg || 'Update failed');
  }
  try {
    return JSON.parse(raw || '{}') as PatchMqExecutionResult;
  } catch {
    return {};
  }
}

export interface DashboardMetrics {
  active_pipeline_value_by_stage: Record<string, string>;
  active_pipeline_currency: string | null;
  tender_count_by_stage: Record<string, number>;
  tenders_with_multiple_quotations: number;
  master_quotation_count_by_execution: Record<string, number>;
  win_loss_counts: Record<string, number>;
  crm_tasks_overdue: number;
  crm_tasks_due_soon: number;
  activity_tasks_overdue: number;
  activity_tasks_due_soon: number;
  closest_to_closure: Record<string, unknown>[];
  bottleneck_stage: string | null;
}

export async function patchPipelineTaskStatus(taskId: string, status: string): Promise<void> {
  const res = await apiFetch(`/api/commercial/pipeline/kanban/tasks/${encodeURIComponent(taskId)}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function fetchDashboardMetrics(scope: ScopeParam): Promise<DashboardMetrics> {
  const res = await apiFetch(`/api/commercial/pipeline/dashboard/metrics?scope=${scope}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
