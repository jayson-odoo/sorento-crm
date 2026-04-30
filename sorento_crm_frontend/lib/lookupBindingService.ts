import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export interface LookupBoundOption {
  value: string;
  label: string;
  keywords: string[];
  is_active: boolean;
}

export interface LookupBoundResponse {
  set_key: string | null;
  set_name: string | null;
  options: LookupBoundOption[];
}

export async function getLookupOptionsByBinding(
  table: string,
  column: string,
): Promise<LookupBoundResponse> {
  const qs = new URLSearchParams({ table, column }).toString();
  const r = await apiFetch(`/api/v1/lookup/by-binding?${qs}`);
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load lookup options'));
  return r.json();
}
