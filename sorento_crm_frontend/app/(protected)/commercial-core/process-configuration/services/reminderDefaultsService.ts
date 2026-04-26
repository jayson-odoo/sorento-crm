import { apiFetch } from '@/lib/api';
import { processConfigPath } from '../lib/apiPaths';

const BASE = () => processConfigPath('reminder-defaults');

export interface ReminderDefaultRow {
  context: string;
  display_name: string;
  rule: Record<string, unknown>;
  sort_order: number;
  created_at?: string;
  updated_at?: string;
}

export async function listReminderDefaults(page = 1, limit = 50) {
  const res = await apiFetch(`${BASE()}?page=${page}&limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch');
  return res.json() as Promise<{
    data: ReminderDefaultRow[];
    pagination: { total: number; page: number; limit: number };
    empty: boolean;
  }>;
}

export async function getReminderDefault(context: string): Promise<ReminderDefaultRow> {
  const res = await apiFetch(`${BASE()}/by-context/${encodeURIComponent(context)}`);
  if (!res.ok) throw new Error('Failed to load');
  return res.json();
}

export async function createReminderDefault(body: {
  context: string;
  display_name: string;
  rule?: Record<string, unknown>;
  sort_order?: number;
}): Promise<ReminderDefaultRow> {
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

export async function updateReminderDefault(
  context: string,
  body: Partial<Pick<ReminderDefaultRow, 'display_name' | 'rule' | 'sort_order'>>,
): Promise<ReminderDefaultRow> {
  const res = await apiFetch(`${BASE()}/by-context/${encodeURIComponent(context)}`, {
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

export async function deleteReminderDefault(context: string): Promise<void> {
  const res = await apiFetch(`${BASE()}/by-context/${encodeURIComponent(context)}`, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { message?: string }).message || 'Delete failed');
  }
}
