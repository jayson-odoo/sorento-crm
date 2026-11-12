import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError, type DataGridParamsInput } from '@/lib/api-client';
import type {
  ScheduledTask,
  ScheduledTaskRun,
  ScheduledTaskUpdateBody,
  ListResponse,
} from '../types/scheduledTask.types';

/** The grid's query: server-side page, sort and search; every filter is multi-value. */
export interface ScheduledTaskListParams extends DataGridParamsInput {
  enabled?: string[];
  last_status?: string[];
  interval_unit?: string[];
}

export async function getScheduledTasks(
  params: ScheduledTaskListParams,
): Promise<ListResponse<ScheduledTask>> {
  const sp = buildDataGridParams(params, {
    enabled: params.enabled?.length ? params.enabled : undefined,
    last_status: params.last_status?.length ? params.last_status : undefined,
    interval_unit: params.interval_unit?.length ? params.interval_unit : undefined,
  });
  const response = await apiFetch(`/api/v1/system/scheduled-tasks?${sp.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to fetch scheduled tasks'));
  return response.json();
}

export async function getScheduledTask(taskId: string): Promise<ScheduledTask> {
  const response = await apiFetch(`/api/v1/system/scheduled-tasks/${taskId}`);
  if (!response.ok) throw new Error('Failed to fetch scheduled task');
  return response.json();
}

export async function updateScheduledTask(
  taskId: string,
  body: ScheduledTaskUpdateBody,
): Promise<ScheduledTask> {
  const response = await apiFetch(`/api/v1/system/scheduled-tasks/${taskId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error('Failed to update scheduled task');
  return response.json();
}

export async function getScheduledTaskRuns(
  taskId: string,
  page: number = 1,
  limit: number = 50,
): Promise<ListResponse<ScheduledTaskRun>> {
  const params = new URLSearchParams({ page: String(page), limit: String(limit) });
  const response = await apiFetch(
    `/api/v1/system/scheduled-tasks/${taskId}/runs?${params.toString()}`,
  );
  if (!response.ok) throw new Error('Failed to fetch task runs');
  return response.json();
}

export async function runScheduledTaskNow(
  taskId: string,
): Promise<{ run_id: string | null; status: string; summary?: Record<string, unknown>; error?: string }> {
  const response = await apiFetch(`/api/v1/system/scheduled-tasks/${taskId}/run-now`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Failed to run task');
  return response.json();
}
