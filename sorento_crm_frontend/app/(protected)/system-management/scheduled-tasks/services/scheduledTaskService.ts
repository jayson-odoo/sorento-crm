import { apiFetch } from '@/lib/api';
import type {
  ScheduledTask,
  ScheduledTaskRun,
  ScheduledTaskUpdateBody,
  ListResponse,
} from '../types/scheduledTask.types';

export async function getScheduledTasks(): Promise<ListResponse<ScheduledTask>> {
  const response = await apiFetch('/api/v1/system/scheduled-tasks');
  if (!response.ok) throw new Error('Failed to fetch scheduled tasks');
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
