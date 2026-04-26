import { apiFetch } from '@/lib/api';
import type { ConfigStageFormData, ConfigStageRow } from '../types/configStage.types';
import { processConfigPath } from '../lib/apiPaths';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export type ConfigStageResource = 'tender-stages' | 'master-quotation-stages' | 'task-statuses';

function base(resource: ConfigStageResource) {
  return processConfigPath(resource);
}

export async function listConfigStages(
  resource: ConfigStageResource,
  params: DataGridApiFetchParams,
): Promise<DataGridApiResponse<ConfigStageRow>> {
  const { pageIndex, pageSize } = params;
  const query = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
  });
  const res = await apiFetch(`${base(resource)}?${query}`);
  if (!res.ok) throw new Error('Failed to fetch');
  const j = (await res.json()) as {
    data: ConfigStageRow[];
    empty: boolean;
    pagination: { total: number; page: number; limit: number };
  };
  return {
    data: j.data,
    empty: j.empty,
    pagination: { total: j.pagination.total, page: j.pagination.page },
  };
}

export async function getConfigStageByCode(resource: ConfigStageResource, code: string): Promise<ConfigStageRow> {
  const enc = encodeURIComponent(code);
  const res = await apiFetch(`${base(resource)}/by-code/${enc}`);
  if (!res.ok) throw new Error('Failed to load');
  return res.json();
}

export async function createConfigStage(resource: ConfigStageResource, body: ConfigStageFormData): Promise<ConfigStageRow> {
  const res = await apiFetch(base(resource), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { message?: string }).message || 'Create failed');
  }
  return res.json();
}

export async function updateConfigStage(
  resource: ConfigStageResource,
  code: string,
  body: Partial<ConfigStageFormData>,
): Promise<ConfigStageRow> {
  const enc = encodeURIComponent(code);
  const res = await apiFetch(`${base(resource)}/by-code/${enc}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { message?: string }).message || 'Update failed');
  }
  return res.json();
}

export async function deleteConfigStage(resource: ConfigStageResource, code: string): Promise<void> {
  const enc = encodeURIComponent(code);
  const res = await apiFetch(`${base(resource)}/by-code/${enc}`, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { message?: string }).message || 'Delete failed');
  }
}
