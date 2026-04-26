import { apiFetch } from '@/lib/api';
import { processConfigPath } from '../lib/apiPaths';

const BASE = () => processConfigPath('activity-templates');

export interface ActivityTemplateRow {
  template_code: string;
  name: string;
  description?: string | null;
  default_duration_days?: number | null;
  priority?: string | null;
  payload: Record<string, unknown>;
  sort_order: number;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export async function listActivityTemplates(page = 1, limit = 50) {
  const res = await apiFetch(`${BASE()}?page=${page}&limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch');
  return res.json() as Promise<{
    data: ActivityTemplateRow[];
    pagination: { total: number; page: number; limit: number };
    empty: boolean;
  }>;
}

export async function getActivityTemplate(code: string): Promise<ActivityTemplateRow> {
  const res = await apiFetch(`${BASE()}/by-code/${encodeURIComponent(code)}`);
  if (!res.ok) throw new Error('Failed to load');
  return res.json();
}

export async function createActivityTemplate(body: {
  template_code: string;
  name: string;
  description?: string;
  default_duration_days?: number | null;
  priority?: string | null;
  payload?: Record<string, unknown>;
  sort_order?: number;
  is_active?: boolean;
}): Promise<ActivityTemplateRow> {
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

export async function updateActivityTemplate(
  code: string,
  body: Partial<Omit<ActivityTemplateRow, 'template_code' | 'created_at' | 'updated_at'>>,
): Promise<ActivityTemplateRow> {
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

export async function deleteActivityTemplate(code: string): Promise<void> {
  const res = await apiFetch(`${BASE()}/by-code/${encodeURIComponent(code)}`, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { message?: string }).message || 'Delete failed');
  }
}
