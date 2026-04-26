import { apiFetch } from '@/lib/api';
import { processConfigPath } from '../lib/apiPaths';

const URL = processConfigPath('settings');

export interface ProcessSettings {
  assignment: Record<string, unknown>;
  reminders: Record<string, unknown>;
  pricing_controls: Record<string, unknown>;
  updated_at?: string | null;
}

export async function getProcessSettings(): Promise<ProcessSettings> {
  const res = await apiFetch(URL);
  if (!res.ok) throw new Error('Failed to load settings');
  return res.json();
}

export async function patchProcessSettings(body: {
  assignment?: Record<string, unknown>;
  reminders?: Record<string, unknown>;
  pricing_controls?: Record<string, unknown>;
}): Promise<ProcessSettings> {
  const res = await apiFetch(URL, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { message?: string }).message || 'Save failed');
  }
  return res.json();
}
