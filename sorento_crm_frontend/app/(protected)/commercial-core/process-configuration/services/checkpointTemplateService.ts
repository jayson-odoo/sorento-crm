import { apiFetch } from '@/lib/api';
import { processConfigPath } from '../lib/apiPaths';

const BASE = () => processConfigPath('tender-checkpoint-templates');

export interface CheckpointTemplateRow {
  checkpoint_code: string;
  name: string;
  sort_order: number;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export async function listCheckpointTemplates(page = 1, limit = 50) {
  const res = await apiFetch(`${BASE()}?page=${page}&limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch');
  return res.json() as Promise<{
    data: CheckpointTemplateRow[];
    pagination: { total: number; page: number; limit: number };
    empty: boolean;
  }>;
}

export async function getCheckpointTemplate(code: string): Promise<CheckpointTemplateRow> {
  const res = await apiFetch(`${BASE()}/by-code/${encodeURIComponent(code)}`);
  if (!res.ok) throw new Error('Failed to load');
  return res.json();
}

export async function createCheckpointTemplate(body: {
  checkpoint_code: string;
  name: string;
  sort_order?: number;
  is_active?: boolean;
}): Promise<CheckpointTemplateRow> {
  const res = await apiFetch(BASE(), {
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

export async function updateCheckpointTemplate(
  code: string,
  body: Partial<Pick<CheckpointTemplateRow, 'name' | 'sort_order' | 'is_active'>>,
): Promise<CheckpointTemplateRow> {
  const res = await apiFetch(`${BASE()}/by-code/${encodeURIComponent(code)}`, {
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

export async function deleteCheckpointTemplate(code: string): Promise<void> {
  const res = await apiFetch(`${BASE()}/by-code/${encodeURIComponent(code)}`, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { message?: string }).message || 'Delete failed');
  }
}
