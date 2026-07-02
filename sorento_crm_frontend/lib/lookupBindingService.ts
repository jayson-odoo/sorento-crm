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
  /** True when the caller lacks permission to read this binding (403). The
   *  field degrades to its free-text fallback instead of erroring — see C4. */
  forbidden?: boolean;
}

export async function getLookupOptionsByBinding(
  table: string,
  column: string,
): Promise<LookupBoundResponse> {
  const qs = new URLSearchParams({ table, column }).toString();
  const r = await apiFetch(`/api/v1/lookup/by-binding?${qs}`);
  // Graceful-degrade on 403: a user who can reach the form but lacks the
  // lookup-read permission should NOT get a thrown error (which react-query
  // retries 4× and a global handler surfaces as a "Permission required" toast).
  // Resolve with an empty/forbidden response so the field falls back to plain
  // input silently — no retry, no toast, no console spam.
  if (r.status === 403) {
    return { set_key: null, set_name: null, options: [], forbidden: true };
  }
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load lookup options'));
  return r.json();
}
