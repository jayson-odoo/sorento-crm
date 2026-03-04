import { apiFetch } from '@/lib/api';

export interface QuickAccessItem {
  id: string;
  path: string;
  label: string | null;
  sort_order: number;
}

const BASE = '/api/user-management/quick-access';

export async function getQuickAccessList(): Promise<QuickAccessItem[]> {
  const res = await apiFetch(BASE);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to fetch quick access');
  }
  return res.json();
}

export async function addQuickAccess(path: string, label?: string | null): Promise<QuickAccessItem> {
  const res = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, label: label ?? null }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to add quick access');
  }
  return res.json();
}

export async function removeQuickAccess(entryId: string): Promise<void> {
  const res = await apiFetch(`${BASE}/${entryId}`, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to remove quick access');
  }
}

export async function reorderQuickAccess(orderedIds: string[]): Promise<QuickAccessItem[]> {
  const res = await apiFetch(`${BASE}/reorder`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ordered_ids: orderedIds }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to reorder quick access');
  }
  return res.json();
}
