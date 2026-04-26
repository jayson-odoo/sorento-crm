import { apiFetch } from '@/lib/api';
import type { WorkflowStageCreatePayload, WorkflowStageRow, WorkflowStageUpdatePayload } from '../types/workflowStage.types';

const BASE = '/api/v1/commercial/workflow-stages';

export async function getWorkflowStages(options?: { domain?: string; includeInactive?: boolean }): Promise<WorkflowStageRow[]> {
  const sp = new URLSearchParams();
  if (options?.domain) sp.set('domain', options.domain);
  if (options?.includeInactive) sp.set('include_inactive', 'true');
  const q = sp.toString();
  const response = await apiFetch(q ? `${BASE}?${q}` : BASE);
  if (!response.ok) throw new Error('Failed to load workflow stages');
  return response.json();
}

export async function updateWorkflowStage(id: string, data: WorkflowStageUpdatePayload): Promise<WorkflowStageRow> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Update failed');
  }
  return response.json();
}

export async function createWorkflowStage(data: WorkflowStageCreatePayload): Promise<WorkflowStageRow> {
  const response = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Create failed');
  }
  return response.json();
}

export async function deleteWorkflowStage(id: string): Promise<void> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}`, { method: 'DELETE' });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Delete failed');
  }
}
