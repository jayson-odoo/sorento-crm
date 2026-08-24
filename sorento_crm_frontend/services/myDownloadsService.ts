/**
 * myDownloadsService - per-user async exports surfaced in the My Downloads drawer.
 *
 * Backend contract:
 *   GET  /api/v1/downloads            -> { downloads: MyDownload[] }
 *   GET  /api/v1/downloads/{id}/url   -> { url, filename }  (409 if not ready)
 *   GET  /api/v1/downloads/{id}/file  -> the bytes, same-origin (409 if not ready)
 *
 * Rows are created by export endpoints (e.g. POST complaints/{id}/export/pdf) and
 * populated asynchronously by RQ tasks.
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * The react-query keys for the two surfaces that show downloads: the top-nav drawer's per-user
 * feed, and the per-entity printer chip. Declared here, in the leaf module both the components
 * and the export TRIGGERS import, so a mutation can refresh the chip it just added a row to
 * without re-typing a literal that would then drift.
 */
export const MY_DOWNLOADS_QUERY_KEY = ['my-downloads'] as const;
export const ENTITY_DOWNLOADS_QUERY_KEY = ['entity-downloads'] as const;

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
  // The 409 body names the status ("Download is not ready (status: processing)"), which is what
  // the row shows the user, so the shared extractor is used rather than a hand-rolled read.
  if (!res.ok) throw new Error(await extractApiError(res, 'Download not ready'));
  return res.json();
}

/**
 * The same-origin path that streams the bytes.
 *
 * A path rather than a fetch because the shared preview modal takes a `downloadUrl` and reads
 * it itself (spreadsheet bytes via `apiFetch`, saves via a blob). The signed URL from `/url` is
 * cross-origin and sends no CORS headers, so it can only be used by elements that load a URL
 * themselves - `<iframe>`, `<img>`, `<video>`.
 */
export function downloadFilePath(id: string): string {
  return `/api/v1/downloads/${id}/file`;
}
