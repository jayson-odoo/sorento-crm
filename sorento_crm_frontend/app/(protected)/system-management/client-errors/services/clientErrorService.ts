import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export interface ClientErrorRow {
  id: string;
  user_id: string | null;
  user_name: string | null;
  boundary: 'global' | 'protected';
  error_name: string | null;
  message: string | null;
  stack: string | null;
  digest: string | null;
  path: string | null;
  build_sha: string | null;
  user_agent: string | null;
  is_chunk_error: boolean;
  client_ts: string | null;
  created_at: string;
}

export interface ClientErrorListResponse {
  data: ClientErrorRow[];
  total: number;
  page: number;
  limit: number;
}

export interface ClientErrorFilters {
  date_from?: string;
  date_to?: string;
  chunk_only?: boolean;
  search?: string;
  page: number;
  limit: number;
}

export async function getClientErrors(filters: ClientErrorFilters): Promise<ClientErrorListResponse> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  });
  const response = await apiFetch(`/api/v1/system/client-errors?${params.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load client errors'));
  return response.json();
}

/** A short browser name for the list column; the drawer shows the full user agent. */
export function browserLabel(ua: string | null): string {
  if (!ua) return '-';
  if (/Edg\//.test(ua)) return 'Edge';
  if (/Firefox\//.test(ua)) return 'Firefox';
  if (/Chrome\/|CriOS\//.test(ua)) return 'Chrome';
  if (/Safari\//.test(ua)) return 'Safari';
  return 'Other';
}
