/**
 * myDownloadsService — per-user async exports surfaced in the My Downloads drawer.
 *
 * Backend contract:
 *   GET  /api/v1/downloads            -> { downloads: MyDownload[] }
 *   GET  /api/v1/downloads/{id}/url   -> { url, filename }  (409 if not ready)
 *
 * Rows are created by export endpoints (e.g. POST complaints/{id}/export/pdf) and
 * populated asynchronously by RQ tasks.
 */

import { apiFetch } from '@/lib/api';

export type MyDownloadStatus = 'pending' | 'processing' | 'ready' | 'failed';

export interface MyDownload {
  id: string;
  kind: string;
  status: MyDownloadStatus;
  filename?: string | null;
  source_entity_type?: string | null;
  source_entity_id?: string | null;
  error?: string | null;
  created_at?: string | null;
  ready_at?: string | null;
}

export interface MyDownloadsResponse {
  downloads: MyDownload[];
}

export async function fetchMyDownloads(limit = 50): Promise<MyDownloadsResponse> {
  const res = await apiFetch(`/api/v1/downloads?limit=${limit}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch downloads (${res.status})`);
  }
  return (await res.json()) as MyDownloadsResponse;
}

/** The current user's downloads tied to one source entity (e.g. a complaint). */
export async function fetchDownloadsForEntity(
  sourceEntityType: string,
  sourceEntityId: string,
  limit = 50,
): Promise<MyDownloadsResponse> {
  const params = new URLSearchParams({
    source_entity_type: sourceEntityType,
    source_entity_id: sourceEntityId,
    limit: String(limit),
  });
  const res = await apiFetch(`/api/v1/downloads?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch downloads (${res.status})`);
  }
  return (await res.json()) as MyDownloadsResponse;
}

export async function fetchDownloadUrl(
  id: string,
): Promise<{ url: string; filename?: string | null }> {
  const res = await apiFetch(`/api/v1/downloads/${id}/url`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: 'Download not ready' }));
    throw new Error(err.detail || err.message || 'Download not ready');
  }
  return res.json();
}
